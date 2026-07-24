from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend import observability  # noqa: E402
from backend.api.main import app  # noqa: E402


class FakeOpenAICompatibleHandler(BaseHTTPRequestHandler):
    chat_requests: list[dict[str, object]] = []

    def log_message(self, *_: object) -> None:
        return None

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("content-length", "0") or "0"))
        if self.path == "/v1/chat/completions":
            self._handle_chat_completion(body)
            return
        if self.path == "/api/public/otel/v1/traces":
            self._write_json(200, {"ok": True})
            return
        self._write_json(404, {"error": "not found"})

    def _handle_chat_completion(self, body: bytes) -> None:
        payload = json.loads(body.decode("utf-8"))
        auth_header = self.headers.get("Authorization")
        self.chat_requests.append(
            {
                "authorization": auth_header,
                "model": payload.get("model"),
                "messages": payload.get("messages", []),
            }
        )
        if auth_header:
            self._write_json(
                401,
                {
                    "error": {
                        "message": "Invalid API key",
                        "type": "authentication_error",
                        "code": "invalid_api_key",
                    }
                },
            )
            return
        self._write_json(
            200,
            {
                "id": "chatcmpl-frontend-test",
                "object": "chat.completion",
                "created": 123,
                "model": payload.get("model"),
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "HRIS adalah sistem informasi HR untuk mendukung proses karyawan. [1]\nFORM_SELECTION: []",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 10,
                    "total_tokens": 22,
                },
            },
        )

    def _write_json(self, status: int, payload: dict[str, object]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class QueryFrontendIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeOpenAICompatibleHandler.chat_requests = []
        self.server = HTTPServer(("127.0.0.1", 0), FakeOpenAICompatibleHandler)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        observability._LANGFUSE_CLIENT = None

    def tearDown(self) -> None:
        observability.shutdown()
        observability._LANGFUSE_CLIENT = None
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=5)
        self.temp_dir.cleanup()

    def test_frontend_query_uses_no_auth_9router_through_langfuse_wrapper(self) -> None:
        store_cache = Mock(return_value="cache-id")
        env = {
            "APP_STATE_DB": str(self.root / "app_state.db"),
            "CONVERSATION_CACHE_DIR": str(self.root / "conversation-cache"),
            "MODEL": "kr/claude-sonnet-4.5",
            "CHAT_BASE_URL": f"{self.base_url}/v1",
            "CHAT_API_KEY": "",
            "OPENAI_API_KEY": "wrong-global-key",
            "OPENAI_COMPAT_NO_AUTH_BASE_URLS": f"{self.base_url}/v1",
            "CHAT_TIMEOUT_SECONDS": "10",
            "MODEL_NUM_PREDICT": "128",
            "CHAT_MAX_TOKENS_FIELD": "max_tokens",
            "LANGFUSE_TRACING_ENABLED": "true",
            "LANGFUSE_PUBLIC_KEY": "pk-lf-test",
            "LANGFUSE_SECRET_KEY": "sk-lf-test",
            "LANGFUSE_BASE_URL": self.base_url,
            "LANGFUSE_HOST": self.base_url,
            "LANGFUSE_TRACING_ENVIRONMENT": "test",
            "LANGFUSE_TRACE_IO_MODE": "masked",
            "TOP_K": "4",
            "SEMANTIC_CACHE_ENABLED": "false",
        }
        citations = [
            {
                "id": 1,
                "source": "SOP HRIS.pdf",
                "page": 2,
                "section": "HRIS",
            }
        ]

        with (
            patch.dict(os.environ, env, clear=False),
            patch("researcher_crew.main.lookup_semantic_cache", return_value=None),
            patch(
                "researcher_crew.main.retrieve_knowledge",
                return_value=("HRIS adalah sistem informasi HR. [1]", citations),
            ),
            patch("researcher_crew.main.store_semantic_cache", store_cache),
            patch("backend.api.routes_public._iter_form_downloads", return_value=[]),
            patch("backend.api.routes_public.find_flowcharts_for_citations", return_value=[]),
            patch("backend.api.routes_public._append_conversation_turn"),
            patch("backend.api.routes_public._record_chat_activity", return_value=123),
        ):
            with TestClient(app) as client:
                response = client.post(
                    "/query",
                    json={
                        "question": "Apa itu HRIS?",
                        "conversation_id": "frontend-test-session",
                    },
                )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["conversation_id"], "frontend-test-session")
        self.assertEqual(payload["answer_source"], "model")
        self.assertEqual(payload["feedback_id"], 123)
        self.assertTrue(payload["feedback_token"])
        self.assertIn("HRIS", payload["answer"])
        self.assertTrue(FakeOpenAICompatibleHandler.chat_requests)
        chat_request = FakeOpenAICompatibleHandler.chat_requests[0]
        self.assertIsNone(chat_request["authorization"])
        self.assertEqual(chat_request["model"], "kr/claude-sonnet-4.5")
        store_cache.assert_called_once()


if __name__ == "__main__":
    unittest.main()
