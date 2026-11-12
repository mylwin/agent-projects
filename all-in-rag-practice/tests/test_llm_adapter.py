"""使用本地 Chat Completions 服务验证配置、LCEL 和 SSE，无真实 API 调用。"""

import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code" / "C8"))

from config import RAGConfig, get_llm_api_key
from langchain_core.documents import Document
from main import RecipeRAGSystem
from rag_modules import GenerationIntegrationModule


class ChatServer(ThreadingHTTPServer):
    def __init__(self):
        self.requests: list[tuple[str, str | None, dict]] = []
        super().__init__(("127.0.0.1", 0), ChatHandler)


class ChatHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        cast(ChatServer, self.server).requests.append(
            (self.path, self.headers.get("Authorization"), payload)
        )
        prompt = "\n".join(m["content"] for m in payload["messages"])
        answer = (
            "detail"
            if "分类结果" in prompt
            else "西红柿炒鸡蛋"
            if "原始查询" in prompt
            else "测试回答"
        )
        base = {"id": "chatcmpl-local", "created": 1, "model": payload["model"]}
        if payload.get("stream"):
            frames = [
                dict(
                    base,
                    object="chat.completion.chunk",
                    choices=[
                        {
                            "index": 0,
                            "delta": {"role": "assistant", "content": answer},
                            "finish_reason": None,
                        }
                    ],
                ),
                dict(
                    base,
                    object="chat.completion.chunk",
                    choices=[
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop",
                        }
                    ],
                ),
            ]
            body = (
                "".join(
                    "data: " + json.dumps(f, ensure_ascii=False) + "\n\n"
                    for f in frames
                )
                + "data: [DONE]\n\n"
            ).encode()
            content_type = "text/event-stream"
        else:
            body = json.dumps(
                dict(
                    base,
                    object="chat.completion",
                    choices=[
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": answer},
                            "finish_reason": "stop",
                        }
                    ],
                ),
                ensure_ascii=False,
            ).encode()
            content_type = "application/json"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class LLMAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ChatServer()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "LLM_BASE_URL": self.url,
                "LLM_API_KEY": "local-test-key",
                "LLM_MODEL": "local-test-model",
            },
            clear=True,
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.server.requests.clear()
        self.docs = [
            Document(
                page_content="西红柿与鸡蛋炒熟。",
                metadata={"dish_name": "西红柿炒鸡蛋"},
            )
        ]

    def assert_requests(self, streaming=False):
        self.assertTrue(self.server.requests)
        for path, auth, payload in self.server.requests:
            self.assertEqual(path, "/v1/chat/completions")
            self.assertEqual(auth, "Bearer local-test-key")
            self.assertEqual(payload["model"], "local-test-model")
            self.assertEqual(payload["max_completion_tokens"], 2048)
            self.assertEqual(bool(payload.get("stream")), streaming)
            self.assertNotIn("stream_options", payload)

    def test_routing_and_rewriting(self):
        module = GenerationIntegrationModule()
        self.assertEqual(module.query_router("怎么做菜？"), "detail")
        self.assertEqual(module.query_rewrite("想做点菜"), "西红柿炒鸡蛋")
        self.assert_requests()

    def test_both_answer_modes(self):
        module = GenerationIntegrationModule()
        self.assertEqual(module.generate_basic_answer("食材？", self.docs), "测试回答")
        self.assertEqual(
            module.generate_step_by_step_answer("怎么做？", self.docs), "测试回答"
        )
        self.assert_requests()

    def test_both_streaming_modes(self):
        module = GenerationIntegrationModule()
        self.assertEqual(
            "".join(module.generate_basic_answer_stream("食材？", self.docs)),
            "测试回答",
        )
        self.assertEqual(
            "".join(module.generate_step_by_step_answer_stream("怎么做？", self.docs)),
            "测试回答",
        )
        self.assert_requests(streaming=True)

    def test_openai_aliases_and_generic_priority(self):
        with patch.dict(
            os.environ,
            {
                "OPENAI_BASE_URL": self.url,
                "OPENAI_API_KEY": "local-test-key",
                "OPENAI_MODEL": "local-test-model",
                "LLM_BASE_URL": " ",
                "LLM_API_KEY": "",
                "LLM_MODEL": "",
            },
            clear=True,
        ):
            config = RAGConfig.from_env()
            config.validate_llm()
            self.assertEqual(config.llm_model, "local-test-model")
            self.assertEqual(
                GenerationIntegrationModule().query_router("怎么做？"), "detail"
            )
            os.environ["LLM_MODEL"] = "preferred-model"
            os.environ["LLM_API_KEY"] = "preferred-key"
            os.environ["LLM_BASE_URL"] = "http://localhost:9999/v1"
            self.assertEqual(RAGConfig.from_env().llm_model, "preferred-model")
            self.assertEqual(
                RAGConfig.from_env().llm_base_url, "http://localhost:9999/v1"
            )
            self.assertEqual(get_llm_api_key(), "preferred-key")
        self.assert_requests()

    def test_missing_configuration_rejected_before_request(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            self.assertRaisesRegex(ValueError, "LLM_API_KEY.*LLM_BASE_URL.*LLM_MODEL"),
        ):
            GenerationIntegrationModule()
        self.assertFalse(self.server.requests)

    def test_invalid_url_rejected(self):
        os.environ["LLM_BASE_URL"] = "not-a-url"
        with self.assertRaisesRegex(ValueError, "LLM_BASE_URL"):
            GenerationIntegrationModule()
        self.assertFalse(self.server.requests)

    def test_constructor_overrides_environment(self):
        module = GenerationIntegrationModule(
            model_name="explicit-model", base_url=self.url + "/custom"
        )
        self.assertEqual(module.model_name, "explicit-model")
        self.assertEqual(module.base_url, self.url + "/custom")
        self.assertFalse(self.server.requests)

    def test_system_requires_initialized_modules(self):
        config = RAGConfig.from_env()
        config.data_path = str(
            Path(__file__).resolve().parents[1] / "data" / "C8" / "cook"
        )
        system = RecipeRAGSystem(config)
        with self.assertRaisesRegex(ValueError, "请先初始化系统"):
            system.build_knowledge_base()
        with self.assertRaisesRegex(ValueError, "请先构建知识库"):
            system.ask_question("怎么做？")
        self.assertFalse(self.server.requests)


if __name__ == "__main__":
    unittest.main()
