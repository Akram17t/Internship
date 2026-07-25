from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = PROJECT_ROOT / "frontend" / "web"


class LogsFrontendStaticTests(unittest.TestCase):
    def test_logs_summary_uses_three_card_view_switcher(self) -> None:
        html = (FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = (FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        logs_js = (FRONTEND_ROOT / "assets" / "js" / "logs.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('id="logsTotalChatCard"', html)
        self.assertIn('id="logsTotalSessionsCard"', html)
        self.assertIn('id="logsFeedbackSummaryCard"', html)
        self.assertEqual(html.count('data-log-view="'), 3)
        self.assertNotIn("Average / Session", html)
        self.assertNotIn("logsTabs", app_js + logs_js + html)
        self.assertNotIn("logsResultCount", app_js + logs_js + html)
        self.assertIn('activeLogsView: "questions"', app_js)
        self.assertIn('selectedLogSessionId: ""', app_js)
        self.assertIn('button?.classList.toggle("is-primary", isActive)', logs_js)

    def test_feedback_view_has_dedicated_reason_stream(self) -> None:
        logs_js = (FRONTEND_ROOT / "assets" / "js" / "logs.js").read_text(
            encoding="utf-8"
        )
        styles = (FRONTEND_ROOT / "assets" / "styles.css").read_text(
            encoding="utf-8"
        )

        self.assertIn('state.activeLogsView === "feedback"', logs_js)
        self.assertIn('params.set("feedback", "negative")', logs_js)
        self.assertIn("createLogFeedbackRow", logs_js)
        self.assertIn("log-feedback-copy", logs_js)
        self.assertIn("log-feedback-reason", logs_js)
        self.assertIn('createLogMessage("Question", question, "user")', logs_js)
        self.assertIn('createLogMessage("Assistant answer", answer, "assistant")', logs_js)
        self.assertIn(".log-feedback-panel .log-message.is-user + .log-message.is-assistant", styles)
        self.assertIn(".logs-screen .log-feedback-icon", styles)
        self.assertIn("border: 0;", styles)
        self.assertNotIn("createLogFeedbackDetail(item.details?.feedback)", logs_js)
        self.assertNotIn("Feedback questions", logs_js)

    def test_session_view_uses_legacy_question_filter_flow(self) -> None:
        html = (FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = (FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        logs_js = (FRONTEND_ROOT / "assets" / "js" / "logs.js").read_text(
            encoding="utf-8"
        )
        styles = (FRONTEND_ROOT / "assets" / "styles.css").read_text(
            encoding="utf-8"
        )

        self.assertIn('id="logsSessionFilter"', html)
        self.assertIn('id="logsClearSessionButton"', html)
        self.assertIn("logsSessionFilter", app_js)
        self.assertIn("logsClearSessionButton", app_js)
        self.assertIn("selectedLogSessionId", logs_js)
        self.assertIn('params.set("conversation_id", state.selectedLogSessionId)', logs_js)
        self.assertIn('elements.logsActiveSessionLabel.textContent = sessionId', logs_js)
        self.assertIn('? "Filtered session"', logs_js)
        self.assertIn('state.activeLogsView = "questions"', logs_js)
        self.assertIn("createLogSessionDeleteButton", logs_js)
        self.assertIn("renderActiveSessionFilter", logs_js)
        self.assertIn("logs-session-open", styles)
        self.assertIn("logs-session-filter", styles)
        self.assertNotIn("activeLogSessionId", logs_js + app_js)
        self.assertNotIn("createLogSessionPanel", logs_js)
        self.assertNotIn("createLogSessionQuestion", logs_js)
        self.assertNotIn("logs-session-toggle", logs_js + styles)

    def test_logs_fetches_up_to_one_thousand_questions(self) -> None:
        logs_js = (FRONTEND_ROOT / "assets" / "js" / "logs.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('new URLSearchParams({ limit: "1000" })', logs_js)
        self.assertNotIn('new URLSearchParams({ limit: "100" })', logs_js)

    def test_naive_log_timestamps_are_not_forced_to_utc(self) -> None:
        logs_js = (FRONTEND_ROOT / "assets" / "js" / "logs.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('return Number.isNaN(date.getTime()) ? null : { date, timeZone: "UTC" };', logs_js)
        self.assertIn("timeZone: parsed.timeZone", logs_js)
        self.assertNotIn("`${rawValue}Z`", logs_js)


if __name__ == "__main__":
    unittest.main()
