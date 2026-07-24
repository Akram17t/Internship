from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

from backend import observability


class ObservabilityTests(unittest.TestCase):
    def test_langfuse_disabled_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(observability.is_enabled())
            self.assertEqual(
                observability.openai_observation_kwargs("generate-response"),
                {},
            )

    def test_langfuse_requires_flag_and_keys(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LANGFUSE_TRACING_ENABLED": "true",
                "LANGFUSE_PUBLIC_KEY": "pk-lf-test",
                "LANGFUSE_BASE_URL": "https://jp.cloud.langfuse.com",
            },
            clear=True,
        ):
            self.assertFalse(observability.is_enabled())

    def test_langfuse_enabled_with_complete_config(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LANGFUSE_TRACING_ENABLED": "true",
                "LANGFUSE_PUBLIC_KEY": "pk-lf-test",
                "LANGFUSE_SECRET_KEY": "sk-lf-test",
                "LANGFUSE_BASE_URL": "https://jp.cloud.langfuse.com",
            },
            clear=True,
        ):
            self.assertTrue(observability.is_enabled())
            kwargs = observability.openai_observation_kwargs(
                "generate-response",
                metadata={"operation": "unit-test"},
            )

        self.assertEqual(kwargs["name"], "generate-response")
        self.assertEqual(kwargs["metadata"], {"operation": "unit-test"})

    def test_redact_masks_sensitive_values_and_truncates_text(self) -> None:
        with patch.dict(
            os.environ,
            {"LANGFUSE_TRACE_IO_MODE": "masked"},
            clear=True,
        ):
            redacted = observability.redact(
                "Email test@example.com token=abc123 "
                "data:image/png;base64,abcdefghijklmnopqrstuvwxyz",
                limit=40,
            )

        self.assertNotIn("test@example.com", str(redacted))
        self.assertNotIn("abc123", str(redacted))
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", str(redacted))
        self.assertIn(
            "[truncated]",
            str(observability.redact("x" * 80, limit=40)),
        )

    def test_trace_context_noops_when_config_missing(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with observability.trace_context(
                name="chat-query",
                session_id="session-test",
                input="Halo",
            ) as trace:
                trace.update(output="ok")

    def test_score_user_thumbs_down_creates_boolean_langfuse_score(self) -> None:
        client = Mock()
        with (
            patch("backend.observability._client", return_value=client),
            patch("backend.observability.environment_name", return_value="test"),
        ):
            scored = observability.score_user_thumbs_down(
                trace_id="0" * 32,
                feedback_id=42,
                reason="Jawaban kurang lengkap.",
                conversation_id="conv-test",
            )

        self.assertTrue(scored)
        client.create_score.assert_called_once_with(
            trace_id="0" * 32,
            name="user-thumbs-down",
            value=0,
            score_id="user-thumbs-down:42",
            data_type="BOOLEAN",
            comment="Jawaban kurang lengkap.",
            metadata={
                "feedback_id": 42,
                "conversation_id": "conv-test",
                "source": "capstone-feedback-modal",
            },
            environment="test",
        )


if __name__ == "__main__":
    unittest.main()
