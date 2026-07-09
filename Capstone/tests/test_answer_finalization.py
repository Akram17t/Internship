from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

RESEARCHER_SRC = Path(__file__).resolve().parents[1] / "backend" / "researcher_crew" / "src"
if str(RESEARCHER_SRC) not in sys.path:
    sys.path.insert(0, str(RESEARCHER_SRC))

from researcher_crew import main as crew_main


class AnswerFinalizationTests(unittest.TestCase):
    def test_strips_trailing_unsupported_sentence_from_supported_answer(self) -> None:
        answer = (
            "Alur kontrol akses diawali dengan permohonan akses dan persetujuan pemilik aset [1].\n"
            f"{crew_main.UNSUPPORTED_ANSWER}"
        )

        cleaned = crew_main._strip_trailing_unsupported_answer(answer)

        self.assertEqual(
            cleaned,
            "Alur kontrol akses diawali dengan permohonan akses dan persetujuan pemilik aset [1].",
        )
        self.assertFalse(crew_main._is_unsupported_answer(cleaned))

    def test_keeps_pure_unsupported_answer_for_no_citation_guard(self) -> None:
        answer = f"{crew_main.UNSUPPORTED_ANSWER} [1]"

        cleaned = crew_main._strip_trailing_unsupported_answer(answer)

        self.assertEqual(cleaned, answer)
        self.assertTrue(crew_main._is_unsupported_answer(cleaned))

    def test_unsupported_flow_returns_without_citations_or_forms(self) -> None:
        store_cache = Mock()

        with (
            patch("researcher_crew.main.lookup_semantic_cache", return_value=None),
            patch(
                "researcher_crew.main.retrieve_knowledge",
                return_value=(
                    "Evidence that was retrieved but does not answer directly.",
                    [
                        {
                            "id": 1,
                            "source": "SOP - Kontrol Akses.pdf",
                            "page": 3,
                            "section": "4. Ketentuan",
                        }
                    ],
                ),
            ),
            patch("researcher_crew.main._generate_answer", return_value=f"{crew_main.UNSUPPORTED_ANSWER} [1]"),
            patch("researcher_crew.main.store_semantic_cache", store_cache),
        ):
            answer, citations, selected_forms = crew_main.run_knowledge_crew(
                "Apa saja aturan yang tidak ada di evidence?",
                trace_id="test",
            )

        self.assertEqual(answer, crew_main.UNSUPPORTED_ANSWER)
        self.assertEqual(citations, [])
        self.assertEqual(selected_forms, [])
        store_cache.assert_not_called()


if __name__ == "__main__":
    unittest.main()
