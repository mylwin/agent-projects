"""使用内存数据库、真实模型 SDK 的 HTTP 替身及流式门闩验证对话。"""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import cast

import httpx
import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage, SystemMessage
from sqlalchemy import Integer, MetaData, Table, create_engine, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session
from sqlalchemy.schema import DefaultClause

from backend.config.database import db_transaction
from backend.config.planner import PlannerSettings
from backend.errors import ApiException
from backend.integrations.chat_model import create_chat_model
from backend.models.conversation_turn import ConversationTurn
from backend.models.generation_run import GenerationRun
from backend.models.model_call import ModelCall
from backend.models.plan_revision import PlanRevision
from backend.models.project import Project
from backend.models.research_report import ResearchReport
from backend.models.tool_evidence import ToolEvidence
from backend.schemas.conversation import (
    ActivityAdjustment,
    AdjustTrip,
    ChatRequest,
    ConversationTurnData,
    GenerateFullPlan,
)
from backend.schemas.trip import Trip
from backend.services import conversation, projects
from backend.services.generation_stream import GenerationStream
from backend.tests.test_api import REQUEST, make_result


@pytest.fixture
def factory():
    """将生产 ORM 映射复制为内存 SQLite，适配驱动但真实执行查询与事务。"""
    engine = create_engine("sqlite://")
    metadata = MetaData()
    for model in (
        Project,
        PlanRevision,
        GenerationRun,
        ResearchReport,
        ToolEvidence,
        ModelCall,
        ConversationTurn,
    ):
        table = cast(Table, model.__table__).to_metadata(metadata)
        for column in table.columns:
            if column.primary_key:
                column.type = Integer()
            if isinstance(column.server_default, DefaultClause):
                column.server_default = (
                    DefaultClause(func.current_timestamp())
                    if "TIMESTAMP" in str(column.server_default.arg)
                    else None
                )
    metadata.create_all(engine)
    result = make_result()
    with Session(engine) as db:
        db.add_all(
            [
                Project(id=12, user_id=1, name="成都", destination="成都"),
                Project(id=99, user_id=2, name="其他用户", destination="苏州"),
            ]
        )
        db.add(
            GenerationRun(
                id=56,
                user_id=1,
                project_id=12,
                status="succeeded",
                request=REQUEST,
                model_name="test",
                map_provider="amap",
            )
        )
        db.add(
            PlanRevision(
                id=34,
                project_id=12,
                number=1,
                title="初稿",
                trip=result.trip.model_dump(mode="json"),
                places=[],
                warnings=result.warnings,
                reply=result.reply,
                generation_run_id=56,
            )
        )
        db.commit()

    class Adapter:
        """同步会话的异步接口替身，不替换任何业务查询。"""

        def __init__(self, db):
            """持有当前短事务。"""
            self.db = db

        async def scalar(self, statement):
            """读取单值。"""
            return self.db.scalar(statement)

        async def scalars(self, statement):
            """读取 ORM 集合。"""
            return self.db.scalars(statement)

        async def execute(self, statement):
            """执行实际 SQL。"""
            return self.db.execute(statement)

        async def get(self, model, key):
            """按主键读取。"""
            return self.db.get(model, key)

        def add(self, model):
            """追踪新记录。"""
            self.db.add(model)

        async def flush(self):
            """实际写入并回填主键。"""
            self.db.flush()

        async def refresh(self, model):
            """刷新数据库默认值。"""
            self.db.refresh(model)

        async def commit(self):
            """提交当前事务。"""
            self.db.commit()

        async def rollback(self):
            """回滚当前事务。"""
            self.db.rollback()

    @asynccontextmanager
    async def sessions():
        """每次提供全新会话，模型调用期间不持有数据库连接。"""
        with Session(engine, expire_on_commit=False) as db:
            yield Adapter(db)

    yield cast(async_sessionmaker[AsyncSession], sessions)
    engine.dispose()


def request(text="你好", generate=False):
    """构造绑定真实依据版本和日期的输入。"""
    return ChatRequest(text=text, base_revision_id=34, day_id=1, generate=generate)


def test_prepare_persists_and_blocks_parallel_turn(factory):
    """同一项目不能并行发言，失败结束后可继续，普通交流不会增加版本。"""

    async def scenario():
        """跨会话核对持久化和并发保护。"""
        context = await conversation.prepare_turn(factory, 1, 12, request())
        with pytest.raises(ApiException) as caught:
            await conversation.prepare_turn(factory, 1, 12, request("第二条"))
        assert caught.value.status_code == 409
        await conversation.finish_turn(factory, context.turn_id, "你好！", "succeeded")
        async with db_transaction(factory) as db:
            turns = await conversation.list_turns(db, 1, 12)
            assert turns[0].assistant_text == "你好！"
            assert len(await projects.projects_crud.list_revisions(db, 12)) == 1
        next_context = await conversation.prepare_turn(
            factory, 1, 12, request("为什么这样安排")
        )
        assert next_context.history[0].id == context.turn_id

    asyncio.run(scenario())


@pytest.mark.parametrize("user_id,project_id", [(2, 12), (1, 99), (1, 123)])
def test_conversation_owner_is_checked(factory, user_id, project_id):
    """越权读取和发言均不泄漏项目内容。"""

    async def scenario():
        """在独立会话中检查两种入口。"""
        with pytest.raises(ApiException) as caught:
            await conversation.prepare_turn(factory, user_id, project_id, request())
        assert caught.value.status_code == 404
        async with db_transaction(factory) as db:
            with pytest.raises(ApiException):
                await conversation.list_turns(db, user_id, project_id)

    asyncio.run(scenario())


def test_real_sdk_chat_keeps_public_context_and_binds_only_adjustment(
    factory, monkeypatch
):
    """真实 ChatOpenAI SDK 流式读取正文；普通聊天只开放局部调整工具。"""
    calls = []

    def respond(http_request):
        """模拟公开正文与供应商推理字段，后者不能混进对话正文。"""
        body = json.loads(http_request.content)
        calls.append(body)
        assert body["stream"] is True
        tools = json.dumps(body.get("tools", []), ensure_ascii=False)
        assert "GenerateFullPlan" not in tools
        assert "AdjustTrip" in tools
        assert "城市慢游" in json.dumps(body, ensure_ascii=False)
        chunks = []
        for content in ("你好，", "可以聊聊当前安排。"):
            chunks.append(
                "data: "
                + json.dumps(
                    {
                        "id": "test",
                        "object": "chat.completion.chunk",
                        "created": 0,
                        "model": "test",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {
                                    "content": content,
                                    "reasoning_content": "不得显示的推理",
                                },
                                "finish_reason": None,
                            }
                        ],
                    },
                    ensure_ascii=False,
                )
                + "\n\n"
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content="".join(chunks) + "data: [DONE]\n\n",
        )

    async def scenario():
        """通过正式 reply 服务及真实 SDK 完成本轮。"""
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(respond)
        ) as mock_http:
            monkeypatch.setattr(
                conversation,
                "create_chat_model",
                lambda settings, _http: create_chat_model(settings, mock_http),
            )
            context = await conversation.prepare_turn(factory, 1, 12, request())
            stream = GenerationStream("test", ())
            result = await conversation.reply(
                factory,
                1,
                12,
                request(),
                context,
                PlannerSettings("test-key", ""),
                asyncio.Semaphore(1),
                stream,
            )
            assert result.data.assistant_text == "你好，可以聊聊当前安排。"
            assert result.data.result_revision_id is None
            events = []
            while not stream.events.empty():
                events.append(stream.events.get_nowait())
            # 本测试在模型完成后才读队列，允许合并尚未发送的旧快照。
            replies = [
                event["message"] for event in events if event["event"] == "reply"
            ]
            assert replies[-1] == "你好，可以聊聊当前安排。"
            assert "不得显示" not in str(events)
        async with db_transaction(factory) as db:
            assert len(await projects.projects_crud.list_revisions(db, 12)) == 1
            assert (await conversation.list_turns(db, 1, 12))[
                0
            ].assistant_text == result.data.assistant_text

    asyncio.run(scenario())
    assert len(calls) == 1


def test_model_messages_use_single_leading_system_message():
    """DashScope 等 OpenAI 兼容接口只允许首条 system 消息。"""
    history = [
        ConversationTurnData(
            id=1,
            base_revision_id=34,
            result_revision_id=None,
            day_id=1,
            generate=False,
            user_text="你好",
            assistant_text="你好，需要我做什么？",
            status="succeeded",
            error_code=None,
            created_at=datetime.now(UTC),
        )
    ]
    context = conversation.ChatContext(1, make_result(), history, True)
    messages = conversation.model_messages(context, request())
    assert isinstance(messages[0], SystemMessage)
    assert not any(isinstance(message, SystemMessage) for message in messages[1:])
    assert isinstance(messages[-1], HumanMessage)
    assert [type(message).__name__ for message in messages[1:]] == [
        "HumanMessage",
        "AIMessage",
        "HumanMessage",
    ]


def test_stream_is_live_and_stop_is_persisted(factory, monkeypatch):
    """收到首段正文时模型尚未结束，关闭连接会保存中断状态并释放并发。"""

    class Model:
        """用门闩保证模型不会提前完成。"""

        def bind_tools(self, tools, **kwargs):
            """普通聊天只绑定局部调整工具。"""
            assert tools == [AdjustTrip]
            return self

        async def astream(self, _messages):
            """先发正文，再等待取消。"""
            yield AIMessageChunk(content="先聊聊你的安排。")
            await asyncio.Event().wait()

    monkeypatch.setattr(conversation, "create_chat_model", lambda *_args: Model())

    async def scenario():
        """逐帧读取，然后模拟用户停止。"""
        context = await conversation.prepare_turn(factory, 1, 12, request())
        stream = GenerationStream("test", ())
        limit = asyncio.Semaphore(1)
        iterator = stream.iterate(
            lambda: conversation.reply(
                factory,
                1,
                12,
                request(),
                context,
                PlannerSettings("key", ""),
                limit,
                stream,
            )
        )
        await anext(iterator)
        frame = await asyncio.wait_for(anext(iterator), timeout=1)
        assert "先聊聊" in frame
        assert limit.locked()
        await iterator.aclose()
        assert not limit.locked()
        async with db_transaction(factory) as db:
            turn = (await conversation.list_turns(db, 1, 12))[0]
            assert turn.status == "cancelled"
            assert turn.assistant_text == "先聊聊你的安排。"

    asyncio.run(scenario())


def test_authorized_full_generation_uses_existing_planner(factory, monkeypatch):
    """显式授权才绑定规划工具，最终版本确实写库并关联本轮对话。"""

    class Model:
        """生成一次合法工具调用。"""

        def bind_tools(self, tools, **kwargs):
            """确认只绑定完整规划工具。"""
            assert tools == [GenerateFullPlan]
            return self

        async def astream(self, _messages):
            """工具参数使用与 CLI 相同的需求契约。"""
            yield AIMessageChunk(
                content="",
                tool_calls=[
                    {"name": "GenerateFullPlan", "args": REQUEST, "id": "tool-1"}
                ],
            )

    async def generate(_request, _settings, on_progress=print, callback=None):
        """替身隔离模型与地图，但保存仍使用正式数据库逻辑。"""
        on_progress("正在研究景点")
        return make_result()

    async def redundant_finish(*_args, **_kwargs):
        raise AssertionError("原子保存成功后不应再打开终态事务")

    monkeypatch.setattr(conversation, "create_chat_model", lambda *_args: Model())
    monkeypatch.setattr(conversation, "generate_trip", generate)
    monkeypatch.setattr(conversation, "finish_turn", redundant_finish)

    async def scenario():
        """实际执行运行创建、规划装配、保存版本和对话完成。"""
        body = request("重新规划", True)
        context = await conversation.prepare_turn(factory, 1, 12, body)
        result = await conversation.reply(
            factory,
            1,
            12,
            body,
            context,
            PlannerSettings("key", "map"),
            asyncio.Semaphore(1),
            GenerationStream("test", ()),
        )
        assert result.data.result_revision_id is not None
        async with db_transaction(factory) as db:
            revisions = await projects.projects_crud.list_revisions(db, 12)
            assert len(revisions) == 2
            assert revisions[0].id == result.data.result_revision_id

    asyncio.run(scenario())


def test_manual_edit_preserves_facts_and_rejects_conflict(factory):
    """文字编辑写新版本，费用/地点不可篡改，旧标签页不能覆盖新版本。"""

    async def scenario():
        """跨短事务验证编辑边界。"""
        trip = make_result().trip
        invalid = trip.model_copy(deep=True)
        invalid.days[0].activities[0].cost = 999
        async with db_transaction(factory) as db:
            with pytest.raises(ApiException) as caught:
                await projects.save_manual_revision(db, 1, 12, 34, invalid)
            assert caught.value.status_code == 422
        trip.days[0].activities[0].title = "手动调整标题"
        async with db_transaction(factory) as db:
            saved = await projects.save_manual_revision(db, 1, 12, 34, trip)
            assert saved.number == 2
            assert saved.result.trip.days[0].activities[0].cost is None
            assert saved.generation_run_id == 56
        async with db_transaction(factory) as db:
            with pytest.raises(ApiException) as caught:
                await projects.save_manual_revision(db, 1, 12, 34, trip)
            assert caught.value.error.code == "revision_conflict"

    asyncio.run(scenario())


def test_deleted_project_includes_conversations(factory):
    """整项删除继续涵盖新增对话表。"""

    async def scenario():
        """创建并完成一轮，再删除项目及其对话。"""
        context = await conversation.prepare_turn(factory, 1, 12, request())
        await conversation.finish_turn(factory, context.turn_id, "你好", "succeeded")
        async with db_transaction(factory) as db:
            await projects.delete_project(db, 1, 12)
        async with db_transaction(factory) as db:
            assert list(await db.scalars(select(ConversationTurn))) == []
            assert await db.get(Project, 99) is not None

    asyncio.run(scenario())


def test_plain_chat_configuration_needs_no_map_key(monkeypatch):
    """缺地图凭据仍能普通聊天，完整生成配置仍严格校验。"""
    monkeypatch.setenv("MODEL_API_KEY", "test-key")
    monkeypatch.setenv("MAP_PROVIDER", "amap")
    monkeypatch.delenv("AMAP_API_KEY", raising=False)
    assert PlannerSettings.from_env(require_maps=False).model_api_key == "test-key"
    with pytest.raises(ValueError, match="AMAP_API_KEY"):
        PlannerSettings.from_env()


def test_expired_turn_does_not_block_next_message(factory):
    """进程异常留下的轮次超过截止时间后，可恢复对话而不永久卡住。"""
    from datetime import timedelta

    async def scenario():
        """把原运行设为过期，再创建下一轮。"""
        context = await conversation.prepare_turn(factory, 1, 12, request())
        async with db_transaction(factory) as db:
            turn = await db.get(ConversationTurn, context.turn_id)
            assert turn is not None
            turn.deadline_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(
                seconds=1
            )
        next_context = await conversation.prepare_turn(factory, 1, 12, request("继续"))
        assert next_context.history[0].status == "failed"
        assert next_context.history[0].error_code == "conversation_interrupted"

    asyncio.run(scenario())


def test_unexpected_tool_call_cannot_generate(factory, monkeypatch):
    """普通聊天即使模型异常返回工具调用，也不能执行规划。"""

    class Model:
        """模拟未遵循协议的模型回复。"""

        def bind_tools(self, tools, **kwargs):
            """普通聊天只绑定局部调整工具。"""
            assert tools == [AdjustTrip]
            return self

        async def astream(self, _messages):
            """返回未授权工具，业务层必须拒绝。"""
            yield AIMessageChunk(
                content="",
                tool_calls=[
                    {"name": "GenerateFullPlan", "args": REQUEST, "id": "unexpected"}
                ],
            )

    monkeypatch.setattr(conversation, "create_chat_model", lambda *_args: Model())

    async def scenario():
        """错误须落盘，并保持原版本数。"""
        context = await conversation.prepare_turn(factory, 1, 12, request())
        with pytest.raises(ApiException):
            await conversation.reply(
                factory,
                1,
                12,
                request(),
                context,
                PlannerSettings("key", ""),
                asyncio.Semaphore(1),
                GenerationStream("test", ()),
            )
        async with db_transaction(factory) as db:
            assert len(await projects.projects_crud.list_revisions(db, 12)) == 1
            assert (await conversation.list_turns(db, 1, 12))[0].status == "failed"

    asyncio.run(scenario())


def test_adjustment_saves_new_revision_and_keeps_facts(factory, monkeypatch):
    """局部调整写新版本，未提供字段保留当前事实。"""

    class Model:
        """返回一次合法的单日调整。"""

        def bind_tools(self, tools, **kwargs):
            """普通聊天只绑定局部调整工具。"""
            assert tools == [AdjustTrip]
            return self

        async def astream(self, _messages):
            """只改时间和标题，省略说明以验证保留原值。"""
            yield AIMessageChunk(
                content="",
                tool_calls=[
                    {
                        "name": "AdjustTrip",
                        "args": {
                            "day_id": 1,
                            "activities": [
                                {
                                    "id": "day-1-activity-1",
                                    "time": "10:30",
                                    "title": "晚点出发",
                                }
                            ],
                        },
                        "id": "adjust-1",
                    }
                ],
            )

    monkeypatch.setattr(conversation, "create_chat_model", lambda *_args: Model())

    async def scenario():
        """通过正式回复服务完成调整，并核对新版本与事实字段。"""
        body = request("第一天下午轻松一点")
        context = await conversation.prepare_turn(factory, 1, 12, body)
        result = await conversation.reply(
            factory,
            1,
            12,
            body,
            context,
            PlannerSettings("key", ""),
            asyncio.Semaphore(1),
            GenerationStream("test", ()),
        )
        assert result.data.status == "succeeded"
        assert result.data.result_revision_id is not None
        assert "已调整第 1 天" in result.data.assistant_text
        async with db_transaction(factory) as db:
            revisions = await projects.projects_crud.list_revisions(db, 12)
            assert len(revisions) == 2
            revision = revisions[0]
            assert revision.id == result.data.result_revision_id
            assert revision.number == 2
            assert revision.title == "助手调整第 1 天"
            assert revision.generation_run_id == 56
            assert revision.places == []
            assert revision.warnings == ["费用待核实"]
            trip = Trip.model_validate(revision.trip)
            activity = trip.days[0].activities[0]
            assert activity.time == "10:30"
            assert activity.title == "晚点出发"
            assert activity.description == "测试活动"
            assert activity.placeId == "place-test"
            assert activity.cost is None
            turns = await conversation.list_turns(db, 1, 12)
            assert turns[-1].result_revision_id == revision.id

    asyncio.run(scenario())


def test_adjustment_without_changes_does_not_create_revision(factory, monkeypatch):
    """模型给出与当前行程相同的内容时不写新版本。"""

    class Model:
        """只回传已有活动 ID，不修改任何字段。"""

        def bind_tools(self, tools, **kwargs):
            """普通聊天只绑定局部调整工具。"""
            assert tools == [AdjustTrip]
            return self

        async def astream(self, _messages):
            """活动顺序和字段都保持原样。"""
            yield AIMessageChunk(
                content="",
                tool_calls=[
                    {
                        "name": "AdjustTrip",
                        "args": {
                            "day_id": 1,
                            "activities": [{"id": "day-1-activity-1"}],
                        },
                        "id": "adjust-noop",
                    }
                ],
            )

    monkeypatch.setattr(conversation, "create_chat_model", lambda *_args: Model())

    async def scenario():
        """成功结束但不产生版本，并说明无需调整。"""
        body = request("这样安排就好")
        context = await conversation.prepare_turn(factory, 1, 12, body)
        result = await conversation.reply(
            factory,
            1,
            12,
            body,
            context,
            PlannerSettings("key", ""),
            asyncio.Semaphore(1),
            GenerationStream("test", ()),
        )
        assert result.data.result_revision_id is None
        assert "没有创建新版本" in result.data.assistant_text
        async with db_transaction(factory) as db:
            assert len(await projects.projects_crud.list_revisions(db, 12)) == 1

    asyncio.run(scenario())


def test_adjustment_rejects_unknown_activity_without_version(factory, monkeypatch):
    """引用不存在活动时校验失败，保留原版本并记录失败轮次。"""

    class Model:
        """返回当前版本不存在的活动 ID。"""

        def bind_tools(self, tools, **kwargs):
            """普通聊天只绑定局部调整工具。"""
            assert tools == [AdjustTrip]
            return self

        async def astream(self, _messages):
            """非法引用必须由业务层拒绝。"""
            yield AIMessageChunk(
                content="",
                tool_calls=[
                    {
                        "name": "AdjustTrip",
                        "args": {
                            "day_id": 1,
                            "activities": [{"id": "day-1-activity-9"}],
                        },
                        "id": "adjust-invalid",
                    }
                ],
            )

    monkeypatch.setattr(conversation, "create_chat_model", lambda *_args: Model())

    async def scenario():
        """调整失败不覆盖已有版本。"""
        body = request("换个活动")
        context = await conversation.prepare_turn(factory, 1, 12, body)
        with pytest.raises(ApiException) as caught:
            await conversation.reply(
                factory,
                1,
                12,
                body,
                context,
                PlannerSettings("key", ""),
                asyncio.Semaphore(1),
                GenerationStream("test", ()),
            )
        assert caught.value.status_code == 422
        assert caught.value.error.code == "invalid_adjustment"
        async with db_transaction(factory) as db:
            assert len(await projects.projects_crud.list_revisions(db, 12)) == 1
            turns = await conversation.list_turns(db, 1, 12)
            assert turns[-1].status == "failed"
            assert turns[-1].error_code == "invalid_adjustment"

    asyncio.run(scenario())


def test_adjustment_requires_latest_revision(factory, monkeypatch):
    """历史版本只能聊天；模型尝试调整时返回版本冲突。"""

    class Model:
        """返回一个格式合法的调整。"""

        def bind_tools(self, tools, **kwargs):
            """普通聊天只绑定局部调整工具。"""
            assert tools == [AdjustTrip]
            return self

        async def astream(self, _messages):
            """调整意图在历史版本上必须被拒绝。"""
            yield AIMessageChunk(
                content="",
                tool_calls=[
                    {
                        "name": "AdjustTrip",
                        "args": {
                            "day_id": 1,
                            "activities": [{"id": "day-1-activity-1"}],
                        },
                        "id": "adjust-history",
                    }
                ],
            )

    monkeypatch.setattr(conversation, "create_chat_model", lambda *_args: Model())

    async def scenario():
        """先插入第二版，再用旧版本发起对话。"""
        async with db_transaction(factory) as db:
            db.add(
                PlanRevision(
                    id=35,
                    project_id=12,
                    number=2,
                    title="第二版",
                    schema_version=1,
                    trip=make_result().trip.model_dump(mode="json"),
                    places=[],
                    warnings=[],
                    reply="",
                    generation_run_id=None,
                )
            )
        body = request("再调整一下")
        context = await conversation.prepare_turn(factory, 1, 12, body)
        with pytest.raises(ApiException) as caught:
            await conversation.reply(
                factory,
                1,
                12,
                body,
                context,
                PlannerSettings("key", ""),
                asyncio.Semaphore(1),
                GenerationStream("test", ()),
            )
        assert caught.value.status_code == 409
        assert caught.value.error.code == "revision_conflict"
        async with db_transaction(factory) as db:
            assert len(await projects.projects_crud.list_revisions(db, 12)) == 2
            turns = await conversation.list_turns(db, 1, 12)
            assert turns[-1].status == "failed"
            assert turns[-1].error_code == "revision_conflict"

    asyncio.run(scenario())


def test_adjusted_trip_removes_omitted_activity_without_mutating_source():
    """未列出的活动被移除，原行程对象保持不变。"""

    trip = make_result().trip.model_copy(deep=True)
    first = trip.days[0].activities[0]
    trip.days[0].activities.append(
        first.model_copy(
            update={"id": "day-1-activity-2", "time": "14:00", "title": "下午散步"}
        )
    )
    adjustment = AdjustTrip(
        day_id=1, activities=[ActivityAdjustment(id=first.id, time="09:30")]
    )
    updated = projects.adjusted_trip(trip, adjustment)
    assert [activity.id for activity in updated.days[0].activities] == [first.id]
    activity = updated.days[0].activities[0]
    assert activity.time == "09:30"
    assert activity.title == first.title
    assert activity.placeId == "place-test"
    assert len(trip.days[0].activities) == 2


def test_adjusted_trip_requires_ordered_unique_times():
    """调整后的时间必须按顺序排列且不能重复。"""

    trip = make_result().trip.model_copy(deep=True)
    first = trip.days[0].activities[0]
    trip.days[0].activities.append(
        first.model_copy(
            update={"id": "day-1-activity-2", "time": "14:00", "title": "下午散步"}
        )
    )
    reversed_times = AdjustTrip(
        day_id=1,
        activities=[
            ActivityAdjustment(id="day-1-activity-2", time="10:00"),
            ActivityAdjustment(id=first.id, time="09:00"),
        ],
    )
    with pytest.raises(ValueError, match="按顺序"):
        projects.adjusted_trip(trip, reversed_times)
    duplicate_times = AdjustTrip(
        day_id=1,
        activities=[
            ActivityAdjustment(id=first.id, time="09:00"),
            ActivityAdjustment(id="day-1-activity-2", time="09:00"),
        ],
    )
    with pytest.raises(ValueError, match="按顺序"):
        projects.adjusted_trip(trip, duplicate_times)


def test_reading_turns_recovers_expired_running_turn(factory):
    """刷新页面读取对话时，超时运行中轮次应显示为失败而不是一直处理中。"""
    from datetime import timedelta

    async def scenario():
        """把运行中轮次改为过期后直接读取。"""
        context = await conversation.prepare_turn(factory, 1, 12, request())
        async with db_transaction(factory) as db:
            turn = await db.get(ConversationTurn, context.turn_id)
            assert turn is not None
            turn.deadline_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(
                seconds=1
            )
        async with db_transaction(factory) as db:
            turns = await conversation.list_turns(db, 1, 12)
        assert turns[-1].status == "failed"
        assert turns[-1].error_code == "conversation_interrupted"

    asyncio.run(scenario())


def test_final_selection_persists_and_late_cancel_does_not_reverse_success(factory):
    """最终版本写回服务端；完成后的取消清理不覆盖成功对话。"""

    async def scenario():
        """先保存成功，再模拟晚到的取消。"""
        context = await conversation.prepare_turn(factory, 1, 12, request())
        await conversation.finish_turn(
            factory, context.turn_id, "完整回复", "succeeded"
        )
        late = await conversation.finish_turn(
            factory, context.turn_id, "部分回复", "cancelled"
        )
        assert late.status == "succeeded"
        assert late.assistant_text == "完整回复"
        async with db_transaction(factory) as db:
            project = await db.get(Project, 12)
            revision = await db.get(PlanRevision, 34)
            assert project is not None and revision is not None
            summary = await projects.choose_final_revision(db, project, revision)
            assert summary.final_revision_id == 34

    asyncio.run(scenario())
