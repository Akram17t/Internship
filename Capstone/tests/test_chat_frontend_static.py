from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHAT_JS = PROJECT_ROOT / "frontend" / "web" / "assets" / "js" / "chat.js"


class ChatFrontendStaticTests(unittest.TestCase):
    def test_query_error_bubble_keeps_feedback_target(self) -> None:
        chat_js = CHAT_JS.read_text(encoding="utf-8")

        self.assertIn("structuredDetail.feedback_id", chat_js)
        self.assertIn("structuredDetail.feedback_token", chat_js)
        self.assertIn("queryError.feedback_id", chat_js)
        self.assertIn("feedback_id: error?.feedback_id || null", chat_js)
        self.assertIn('feedback_token: error?.feedback_token || ""', chat_js)
        self.assertIn("window.localStorage.setItem(CONVERSATION_STORAGE_KEY", chat_js)


if __name__ == "__main__":
    unittest.main()
