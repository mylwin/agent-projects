"""用真实事务和故障注入验证生成互斥、失效回收与对话原子提交。"""

import asyncio
from datetime import timedelta

import pytest

from backend.config.database import db_transaction
from backend.crud import conversation as conversation_crud
from backend.errors import ApiException
from backend.models.conversation_turn import ConversationTurn
from backend.models.generation_run import GenerationRun
from backend.schemas.conversation import ActivityAdjustment, AdjustTrip
from backend.schemas.trip import TripRequest
from backend.services import conversation, projects, saved_generation
from backend.tests import test_conversation
from backend.tests.test_api import REQUEST, make_result

factory = test_conversation.factory


@pytest.mark.parametrize("occupied", ["conversation", "generation"])
def test_direct_generation_respects_project_reservation(factory, occupied):
    """直接生成入口不能绕过对话或另一生成运行的项目级互斥。"""

    async def scenario():
        body = TripRequest.model_validate(REQUEST)
        if occupied == "conversation":
            await conversation.prepare_turn(factory, 1, 12, test_conversation.request())
        else:
            await saved_generation.start_run(factory, 1, 12, body, "model", "amap")
        with pytest.raises(ApiException) as caught:
            await saved_generation.start_run(factory, 1, 12, body, "model", "amap")
        assert caught.value.error.code == "project_busy"
        async with db_transaction(factory) as db:
            assert len(await projects.projects_crud.list_revisions(db, 12)) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("action", ["chat", "edit", "delete"])
@pytest.mark.parametrize("legacy", [False, True])
def test_orphan_generation_no_longer_blocks_project(factory, action, legacy):
    """刷新、编辑和删除都能回收遗留运行，包括没有截止时间的旧记录。"""

    async def scenario():
        body = TripRequest.model_validate(REQUEST)
        context = await conversation.prepare_turn(
            factory, 1, 12, test_conversation.request(generate=True)
        )
        run_id = await saved_generation.start_run(
            factory, 1, 12, body, "model", "amap", turn_id=context.turn_id
        )
        expired = saved_generation.utc_now() - timedelta(seconds=1)
        async with db_transaction(factory) as db:
            run = await db.get(GenerationRun, run_id)
            turn = await db.get(ConversationTurn, context.turn_id)
            assert run is not None and turn is not None
            run.deadline_at = None if legacy else expired
            turn.deadline_at = expired
        if action == "chat":
            async with db_transaction(factory) as db:
                turns = await conversation.list_turns(db, 1, 12)
                run = await db.get(GenerationRun, run_id)
                assert turns[-1].status == "failed"
                assert run is not None and run.status == "failed"
            await conversation.prepare_turn(factory, 1, 12, test_conversation.request())
        elif action == "edit":
            async with db_transaction(factory) as db:
                await projects.save_manual_revision(db, 1, 12, 34, make_result().trip)
                run = await db.get(GenerationRun, run_id)
                assert run is not None and run.status == "failed"
        else:
            async with db_transaction(factory) as db:
                await projects.delete_project(db, 1, 12)
                assert await projects.projects_crud.get_project(db, 1, 12) is None

    asyncio.run(scenario())


@pytest.mark.parametrize("full", [False, True])
@pytest.mark.parametrize("interruption", [RuntimeError, asyncio.CancelledError])
def test_version_and_conversation_commit_atomically(
    factory, monkeypatch, full, interruption
):
    """在保存对话时注入失败，整个新版本回滚；成功后无需第二次提交终态。"""

    async def scenario():
        body = TripRequest.model_validate(REQUEST)
        context = await conversation.prepare_turn(
            factory, 1, 12, test_conversation.request(generate=full)
        )
        run_id = None
        if full:
            run_id = await saved_generation.start_run(
                factory, 1, 12, body, "model", "amap", turn_id=context.turn_id
            )
        activity = context.result.trip.days[0].activities[0]
        adjustment = AdjustTrip(
            day_id=1,
            activities=[ActivityAdjustment(id=activity.id, title="调整后的活动")],
        )

        async def save():
            if full:
                assert run_id is not None
                return await saved_generation.save_result(
                    factory,
                    1,
                    12,
                    None,
                    body,
                    run_id,
                    make_result(),
                    [],
                    turn_id=context.turn_id,
                )
            return await projects.save_assistant_adjustment(
                factory, 1, 12, context.turn_id, adjustment, "已处理建议"
            )

        original = conversation_crud.save_turn_result

        async def fail_after_write(*args, **kwargs):
            await original(*args, **kwargs)
            raise interruption("模拟提交前退出")

        with monkeypatch.context() as patch:
            patch.setattr(conversation_crud, "save_turn_result", fail_after_write)
            with pytest.raises(interruption, match="模拟提交前退出"):
                await save()
        async with db_transaction(factory) as db:
            assert len(await projects.projects_crud.list_revisions(db, 12)) == 1
            turn = await db.get(ConversationTurn, context.turn_id)
            assert turn is not None and turn.status == "running"
            assert turn.result_revision_id is None
            if run_id is not None:
                run = await db.get(GenerationRun, run_id)
                assert run is not None and run.status == "running"
        await save()
        async with db_transaction(factory) as db:
            turns = await conversation.list_turns(db, 1, 12)
            revisions = await projects.projects_crud.list_revisions(db, 12)
            assert len(revisions) == 2
            assert turns[-1].status == "succeeded"
            assert turns[-1].result_revision_id == revisions[0].id
        late = await conversation.finish_turn(
            factory, context.turn_id, "中断", "cancelled"
        )
        assert late.status == "succeeded"
        assert late.result_revision_id is not None

    asyncio.run(scenario())


@pytest.mark.parametrize("full", [False, True])
def test_expired_work_cannot_commit_after_new_request(factory, full):
    """旧工作即使随后返回，也不能越过截止时间给新请求追加版本。"""

    async def scenario():
        body = TripRequest.model_validate(REQUEST)
        context = await conversation.prepare_turn(
            factory, 1, 12, test_conversation.request(generate=full)
        )
        run_id = None
        if full:
            run_id = await saved_generation.start_run(
                factory, 1, 12, body, "model", "amap", turn_id=context.turn_id
            )
        async with db_transaction(factory) as db:
            turn = await db.get(ConversationTurn, context.turn_id)
            assert turn is not None
            turn.deadline_at = saved_generation.utc_now() - timedelta(seconds=1)
            if run_id is not None:
                run = await db.get(GenerationRun, run_id)
                assert run is not None
                run.deadline_at = turn.deadline_at
        await conversation.prepare_turn(factory, 1, 12, test_conversation.request())
        with pytest.raises(ApiException) as caught:
            if full:
                assert run_id is not None
                await saved_generation.save_result(
                    factory,
                    1,
                    12,
                    None,
                    body,
                    run_id,
                    make_result(),
                    [],
                    turn_id=context.turn_id,
                )
            else:
                item = context.result.trip.days[0].activities[0]
                adjustment = AdjustTrip(
                    day_id=1,
                    activities=[ActivityAdjustment(id=item.id, title="不应保存")],
                )
                await projects.save_assistant_adjustment(
                    factory, 1, 12, context.turn_id, adjustment, ""
                )
        assert caught.value.error.code == "conversation_interrupted"
        async with db_transaction(factory) as db:
            assert len(await projects.projects_crud.list_revisions(db, 12)) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("full", [False, True])
def test_deadline_is_rechecked_after_turn_flush(factory, monkeypatch, full):
    """保存过程跨过截止时间时，已flush的新版本及终态仍整体回滚。"""

    async def scenario():
        body = TripRequest.model_validate(REQUEST)
        context = await conversation.prepare_turn(
            factory, 1, 12, test_conversation.request(generate=full)
        )
        run_id = None
        if full:
            run_id = await saved_generation.start_run(
                factory, 1, 12, body, "model", "amap", turn_id=context.turn_id
            )
        original = conversation_crud.save_turn_result

        async def expire_clock(db, turn, **kwargs):
            await original(db, turn, **kwargs)
            expired = turn.deadline_at + timedelta(seconds=1)
            monkeypatch.setattr(saved_generation, "utc_now", lambda: expired)

            class Clock:
                @staticmethod
                def now(_tz):
                    return expired

            monkeypatch.setattr(projects, "datetime", Clock)

        monkeypatch.setattr(conversation_crud, "save_turn_result", expire_clock)
        with pytest.raises(ApiException):
            if full:
                assert run_id is not None
                await saved_generation.save_result(
                    factory,
                    1,
                    12,
                    None,
                    body,
                    run_id,
                    make_result(),
                    [],
                    turn_id=context.turn_id,
                )
            else:
                item = context.result.trip.days[0].activities[0]
                adjustment = AdjustTrip(
                    day_id=1,
                    activities=[ActivityAdjustment(id=item.id, title="不应保存")],
                )
                await projects.save_assistant_adjustment(
                    factory, 1, 12, context.turn_id, adjustment, ""
                )
        async with db_transaction(factory) as db:
            assert len(await projects.projects_crud.list_revisions(db, 12)) == 1
            turn = await db.get(ConversationTurn, context.turn_id)
            assert turn is not None and turn.status == "running"
            assert turn.result_revision_id is None

    asyncio.run(scenario())


def test_expired_direct_run_cannot_create_project(factory):
    """无所属项目的新建运行过期后，也不能创建项目或版本。"""

    async def scenario():
        body = TripRequest.model_validate(REQUEST)
        run_id = await saved_generation.start_run(
            factory, 1, None, body, "model", "amap"
        )
        async with db_transaction(factory) as db:
            run = await db.get(GenerationRun, run_id)
            assert run is not None
            run.deadline_at = saved_generation.utc_now() - timedelta(seconds=1)
        with pytest.raises(ApiException) as caught:
            await saved_generation.save_result(
                factory, 1, None, "不应创建", body, run_id, make_result(), []
            )
        assert caught.value.error.code == "generation_interrupted"
        async with db_transaction(factory) as db:
            listed = await projects.list_projects(db, 1, 1, 100)
            assert len(listed.items) == 1

    asyncio.run(scenario())
