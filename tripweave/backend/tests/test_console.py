"""验证真实分片到达时即可显示，工具进度和失败诊断不污染结果 JSON。"""

import asyncio
import io
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_openai import ChatOpenAI
from mcp.shared.memory import create_connected_server_and_client_session

from backend.agents.console import ConsoleCallback
from backend.agents.planner import create_draft
from backend.config.planner import PlannerSettings
from backend.errors import PlanningError
from backend.integrations.chat_model import create_chat_model
from backend.integrations.map_mcp import MapTools
from backend.schemas.trip import Place
from backend.services.planning import generate_trip, plan_trip
from backend.tests.test_planning import ModelStub, make_draft, make_request, make_server


def frame(delta: dict, finish: str | None = None) -> bytes:
    """编码一条合成的 OpenAI 兼容 SSE 分片。"""
    data = {
        "id": "test",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "test",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    return ("data: " + json.dumps(data) + "\n\n").encode()


@pytest.mark.parametrize("thinking", [False, True])
def test_text_streams_before_completion_with_openai_only(thinking: bool) -> None:
    """思考开关不切换客户端，正文在完整响应返回前即可显示。"""
    output = io.StringIO()
    console = ConsoleCallback(output)
    requests = []

    class LiveStream(httpx.AsyncByteStream):
        """每发送一段，先确认上一段已到达终端。"""

        def __init__(self) -> None:
            """与网络流一样只消费一次，SDK 清理时不能重新发送分片。"""
            self.started = False

        async def __aiter__(self):
            """不等完整结果返回才检查显示，避免伪流式测试。"""
            if self.started:
                return
            self.started = True
            yield frame({"role": "assistant", "content": "第一"})
            assert "第一" in output.getvalue()
            assert "第一段" not in output.getvalue()
            yield frame({"content": "段"}, "stop")
            yield b"data: [DONE]\n\n"

    def respond(request: httpx.Request) -> httpx.Response:
        """检查仍使用配置中的模型、地址与思考参数。"""
        requests.append(request)
        body = json.loads(request.content)
        assert body["model"] == "configured-model"
        assert body["enable_thinking"] is thinking
        assert request.url.host == "model.test"
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=LiveStream()
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            model = create_chat_model(
                PlannerSettings(
                    "test",
                    "test",
                    model_name="configured-model",
                    model_base_url="https://model.test/v1",
                    model_enable_thinking=thinking,
                ),
                http,
                console,
            )
            assert type(model) is ChatOpenAI
            result = await model.ainvoke("测试", config={"tags": ["agent:weather"]})
            assert result.text == "第一段"

    asyncio.run(run())
    assert len(requests) == 1
    assert output.getvalue().count("第一段") == 1
    assert "[天气研究·回复]" in output.getvalue()
    assert "[天气研究·推理]" not in output.getvalue()


def test_final_response_printed_when_streaming_has_no_text() -> None:
    """没有流式正文时，回调补打最终响应，避免终端只显示工具进度。"""
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, LLMResult

    output = io.StringIO()
    console = ConsoleCallback(output)
    asyncio.run(console.on_chat_model_start({}, [], tags=["agent:weather"]))
    response = LLMResult(
        generations=[[ChatGeneration(message=AIMessage(content="天气研究结论"))]]
    )
    asyncio.run(console.on_llm_end(response, tags=["agent:weather"]))
    assert "[天气研究·回复] 天气研究结论" in output.getvalue()


@pytest.mark.parametrize("debug", [False, True])
def test_planner_tool_arguments_are_optional(debug: bool) -> None:
    """同一次规划可选择显示 JSON 参数，最终结构化结果和调用次数不变。"""
    output = io.StringIO()
    console = ConsoleCallback(output, debug_tools=debug)
    body = json.dumps(make_draft())
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        """将结构化工具参数拆成两段返回。"""
        requests.append(request)
        payload = frame(
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "draft",
                        "type": "function",
                        "function": {"name": "TravelDraft", "arguments": body[:20]},
                    }
                ],
            }
        )
        payload += frame(
            {"tool_calls": [{"index": 0, "function": {"arguments": body[20:]}}]},
            "tool_calls",
        )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=payload + b"data: [DONE]\n\n",
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            model = create_chat_model(PlannerSettings("test", "test"), http, console)
            place = Place(
                id="test-poi",
                name="合成地点",
                address="",
                longitude=104,
                latitude=30,
                fetched_at=datetime.now(UTC),
            )
            draft = await create_draft(make_request(), [place], model)
            assert len(draft.days) == 1

    asyncio.run(run())
    assert len(requests) == 1
    assert "[行程规划]" in output.getvalue()
    assert ("place_id" in output.getvalue()) is debug


@pytest.mark.parametrize("thinking", [False, True])
@pytest.mark.parametrize("fail_weather", [False, True])
def test_all_agents_stream_and_tools_are_not_duplicated(
    thinking: bool, fail_weather: bool
) -> None:
    """回调传给 Agent 后同时覆盖工具与模型，正文不被打印两遍。"""
    output = io.StringIO()
    console = ConsoleCallback(output)
    stub = ModelStub()

    async def run() -> None:
        async with create_connected_server_and_client_session(
            make_server(fail_weather=fail_weather)
        ) as session:
            tools = await load_mcp_tools(session)
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(stub.respond)
            ) as http:
                result = await plan_trip(
                    make_request(),
                    create_chat_model(
                        PlannerSettings("test", "test", model_enable_thinking=thinking),
                        http,
                        console,
                    ),
                    MapTools("amap", tools),
                    console.progress,
                )
                assert result.trip.days

    asyncio.run(run())
    text = output.getvalue()
    assert len(stub.calls) == 7
    assert text.count("已查询工具，未覆盖的日期和价格保持未知。") == 3
    for role in ["景点研究", "天气研究", "住宿研究"]:
        assert text.count(f"[{role}] 工具开始：") == 1
        if role == "天气研究" and fail_weather:
            assert text.count(f"[{role}] 工具失败：") == 1
        else:
            assert text.count(f"[{role}] 工具完成：") == 1
    assert "[行程规划] 模型开始生成" in text


def test_grouped_failure_keeps_stage_and_redacts_credentials() -> None:
    """MCP 包装后的原始异常类型、状态和阶段可见，凭据与 URL 不可见。"""
    secret = "private-test-key"
    original = httpx.HTTPStatusError(
        f"401 Unauthorized; https://service.test/mcp?key={secret}; {secret}",
        request=httpx.Request("POST", "https://service.test"),
        response=httpx.Response(401),
    )
    nested = ExceptionGroup(
        "MCP 包装",
        [ExceptionGroup("SDK 包装", [PlanningError("weather 研究", original)])],
    )

    class Client:
        """不访问网络的 MCP 会话。"""

        @asynccontextmanager
        async def session(self, *args: object):
            """允许进入模型阶段以验证外层统一诊断。"""
            yield None

    with (
        patch("backend.services.planning.create_map_mcp", return_value=Client()),
        patch(
            "backend.services.planning.load_mcp_tools", new=AsyncMock(return_value=[])
        ),
        patch("backend.services.planning.plan_trip", new=AsyncMock(side_effect=nested)),
    ):
        with pytest.raises(PlanningError) as caught:
            asyncio.run(generate_trip(make_request(), PlannerSettings(secret, secret)))
    message = str(caught.value)
    assert (
        "weather 研究" in message and "HTTPStatusError" in message and "401" in message
    )
    assert secret not in message and "https://" not in message


def test_cli_failure_preserves_empty_stdout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """失败时进度和原因只写 stderr，不输出成功 JSON。"""
    from backend.__main__ import main
    from backend.tests.test_planning import ROOT

    monkeypatch.setattr(
        "sys.argv", ["backend", str(ROOT / "examples/trip-request.json")]
    )
    monkeypatch.setattr(
        PlannerSettings, "from_env", lambda: PlannerSettings("test", "test")
    )
    monkeypatch.setattr(
        "backend.__main__.generate_trip",
        AsyncMock(
            side_effect=PlanningError("weather 研究", ValueError("合成工具参数无效"))
        ),
    )
    assert main() == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "weather 研究" in output.err and "ValueError" in output.err
    assert "合成工具参数无效" in output.err


@pytest.mark.parametrize(
    "message,secret",
    [
        ("Authorization: Bearer unknown-token", "unknown-token"),
        ('{"api_key": "unknown-token"}', "unknown-token"),
        ("失败地址 https://service.test/mcp?ak=unknown-token", "unknown-token"),
    ],
)
def test_diagnostics_redact_unknown_authentication_fields(
    message: str, secret: str
) -> None:
    """即使不是本地配置的密钥，常见认证字段也不能进入终端。"""
    from backend.errors import redact

    assert secret not in redact(message)


def test_native_reasoning_block_is_printed_once() -> None:
    """标准推理块与兼容字段同时存在时不重复显示。"""
    from langchain_core.messages import AIMessageChunk
    from langchain_core.outputs import ChatGenerationChunk

    output = io.StringIO()
    console = ConsoleCallback(output)
    chunk = ChatGenerationChunk(
        message=AIMessageChunk(
            content=[{"type": "reasoning", "reasoning": "公开摘要"}],
            additional_kwargs={"reasoning_content": "公开摘要"},
        )
    )
    asyncio.run(console.on_llm_new_token("", chunk=chunk, tags=["agent:planner"]))
    assert output.getvalue().count("公开摘要") == 1
    assert "[行程规划·推理]" in output.getvalue()
