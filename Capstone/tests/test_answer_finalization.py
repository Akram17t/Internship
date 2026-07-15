from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

RESEARCHER_SRC = Path(__file__).resolve().parents[1] / "backend" / "researcher_crew" / "src"
if str(RESEARCHER_SRC) not in sys.path:
    sys.path.insert(0, str(RESEARCHER_SRC))

from backend.answer_policy import is_unsupported_answer, unsupported_answer_text
from researcher_crew import main as crew_main


class AnswerFinalizationTests(unittest.TestCase):
    def test_strip_thinking_blocks_removes_qwen_reasoning(self) -> None:
        answer = crew_main._strip_thinking_blocks(
            "<think>\nreasoning yang tidak boleh tampil\n</think>\nJawaban final [1]."
        )

        self.assertEqual(answer, "Jawaban final [1].")

    def test_finalize_answer_citations_replaces_invalid_marker(self) -> None:
        answer, citations = crew_main._finalize_answer_citations(
            "Jawaban didukung sumber [99].",
            [{"id": 1, "source": "SOP.pdf"}],
        )

        self.assertEqual(answer, "Jawaban didukung sumber [1].")
        self.assertEqual(citations, [{"id": 1, "source": "SOP.pdf"}])

    def test_faq_prompt_requests_compact_but_informative_answer(self) -> None:
        with patch(
            "researcher_crew.main._ollama_generate",
            return_value="Jawaban FAQ yang padat dan bersumber [1].",
        ) as generate:
            answer = crew_main._generate_faq_answer(
                "Bagaimana proses perjalanan dinas?",
                "[1] Requestor mengisi form dan meminta persetujuan.",
            )

        prompt = generate.call_args.args[0]
        self.assertIn("3-6 bullet", prompt)
        self.assertIn("80-150 kata", prompt)
        self.assertIn("semua detail material", prompt)
        self.assertEqual(answer, "Jawaban FAQ yang padat dan bersumber [1].")

    def test_form_selection_with_markdown_label_is_removed(self) -> None:
        answer = "Jawaban bersumber [1].\n\n**FORM_SELECTION:** []"

        cleaned, selected_forms = crew_main._split_form_selection(answer)

        self.assertEqual(cleaned, "Jawaban bersumber [1].")
        self.assertEqual(selected_forms, [])

    def test_form_selection_wrapped_in_markdown_is_parsed(self) -> None:
        answer = (
            'Gunakan form berikut [1].\n'
            '**FORM_SELECTION: ["Form - Perjalanan Dinas (Template).pdf"]**'
        )

        cleaned, selected_forms = crew_main._split_form_selection(answer)

        self.assertEqual(cleaned, "Gunakan form berikut [1].")
        self.assertEqual(
            selected_forms,
            ["Form - Perjalanan Dinas (Template).pdf"],
        )

    def test_rewrite_keeps_original_when_ai_rewrites_standalone_question(self) -> None:
        with patch(
            "researcher_crew.main._ollama_generate",
            return_value="REWRITE: HRIS itu apa sih?",
        ) as generate:
            rewritten = crew_main._rewrite_query(
                "HRIS tuh apa sih?",
                "Percakapan sebelumnya yang panjang.",
            )

        self.assertEqual(rewritten, "HRIS tuh apa sih?")
        generate.assert_called_once()

    def test_rewrite_prompt_emphasizes_keep_for_standalone_travel_allowance_question(self) -> None:
        with patch(
            "researcher_crew.main._ollama_generate",
            return_value="KEEP",
        ) as generate:
            rewritten = crew_main._rewrite_query(
                "Tolong sebutin nominal uang saku dan uang makan selama perjalanan dinas",
                "Percakapan membahas perjalanan dinas dalam negeri.",
            )

        prompt = generate.call_args.args[0]
        self.assertIn("JANGAN PERNAH mengganti, mempersempit", prompt)
        self.assertIn("Riwayat hanya boleh dipakai untuk mengisi subjek yang hilang", prompt)
        self.assertIn("Tolong sebutin nominal uang saku dan uang makan selama perjalanan dinas", prompt)
        self.assertIn("Jawaban: KEEP", prompt)
        self.assertEqual(
            rewritten,
            "Tolong sebutin nominal uang saku dan uang makan selama perjalanan dinas",
        )
        generate.assert_called_once()

    def test_rewrite_uses_llm_for_explicit_context_reference(self) -> None:
        with patch(
            "researcher_crew.main._ollama_generate",
            return_value="REWRITE: Form apa yang dipakai untuk perjalanan dinas?",
        ) as generate:
            rewritten = crew_main._rewrite_query(
                "Form apa yang dipakai untuk itu?",
                "Percakapan membahas perjalanan dinas.",
            )

        self.assertEqual(
            rewritten,
            "Form apa yang dipakai untuk perjalanan dinas?",
        )
        generate.assert_called_once()

    def test_rewrite_supports_implicit_context_reference(self) -> None:
        with patch(
            "researcher_crew.main._ollama_generate",
            return_value="REWRITE: Kalau perjalanan dinas luar negeri gimana?",
        ):
            rewritten = crew_main._rewrite_query(
                "Kalau luar negeri gimana?",
                "Percakapan membahas perjalanan dinas dalam negeri.",
            )

        self.assertEqual(
            rewritten,
            "Kalau perjalanan dinas luar negeri gimana?",
        )

    def test_rewrite_rejects_unstructured_ai_rephrasing(self) -> None:
        with patch(
            "researcher_crew.main._ollama_generate",
            return_value="HRIS itu apa sih?",
        ):
            rewritten = crew_main._rewrite_query(
                "HRIS tuh apa sih?",
                "Percakapan membahas resign.",
            )

        self.assertEqual(rewritten, "HRIS tuh apa sih?")

    def test_rewrite_rejects_topic_swap_when_subject_already_stated(self) -> None:
        # 'itu' hanya partikel pengisi di sini; subjek 'resign' sudah eksplisit.
        # Rewrite yang mengganti 'resign' jadi 'perjalanan dinas' harus ditolak.
        with patch(
            "researcher_crew.main._ollama_generate",
            return_value=(
                "REWRITE: Kalau gue mau perjalanan dinas, "
                "alur yang harus dijalani gimana?"
            ),
        ) as generate:
            rewritten = crew_main._rewrite_query(
                "Kalau gue mau resign, alur yang harus dijalani itu gimana?",
                "Percakapan membahas alur pengajuan perjalanan dinas.",
            )

        self.assertEqual(
            rewritten,
            "Kalau gue mau resign, alur yang harus dijalani itu gimana?",
        )
        generate.assert_called_once()

    def test_rewrite_is_safe_allows_pure_dereference(self) -> None:
        # De-referensi yang benar hanya menambah subjek, tidak membuang kata konten.
        self.assertTrue(
            crew_main._rewrite_is_safe(
                "Form apa yang dipakai untuk itu?",
                "Form apa yang dipakai untuk resign?",
            )
        )

    def test_rewrite_is_safe_rejects_dropped_content_word(self) -> None:
        self.assertFalse(
            crew_main._rewrite_is_safe(
                "Kalau gue mau resign, alur yang harus dijalani itu gimana?",
                "Kalau gue mau perjalanan dinas, alur yang harus dijalani gimana?",
            )
        )

    def test_rewrite_is_safe_rejects_scope_injection_for_standalone_question(self) -> None:
        self.assertFalse(
            crew_main._rewrite_is_safe(
                "Dalam manajemen insiden, tugas dan tanggung jawab tiap role itu seperti apa?",
                "Dalam manajemen insiden, tugas dan tanggung jawab tiap role dalam administrasi karyawan itu seperti apa?",
            )
        )

    def test_rewrite_keeps_standalone_question_when_ai_adds_unrelated_context(self) -> None:
        with patch(
            "researcher_crew.main._ollama_generate",
            return_value=(
                "REWRITE: Apakah ada data perusahaan yang benar-benar nggak boleh "
                "dibagikan? Jelasin juga batasan sharing data itu sampai mana "
                "dalam konteks administrasi karyawan baru"
            ),
        ):
            rewritten = crew_main._rewrite_query(
                "Apakah ada data perusahaan yang benar-benar nggak boleh dibagikan? "
                "Jelasin juga batasan sharing data itu sampai mana",
                "Percakapan sebelumnya membahas administrasi karyawan baru.",
            )

        self.assertEqual(
            rewritten,
            "Apakah ada data perusahaan yang benar-benar nggak boleh dibagikan? "
            "Jelasin juga batasan sharing data itu sampai mana",
        )

    def test_strips_trailing_unsupported_sentence_from_supported_answer(self) -> None:
        answer = (
            "Alur kontrol akses diawali dengan permohonan akses dan persetujuan pemilik aset [1].\n"
            f"{unsupported_answer_text()}"
        )

        cleaned = crew_main._strip_trailing_unsupported_answer(answer)

        self.assertEqual(
            cleaned,
            "Alur kontrol akses diawali dengan permohonan akses dan persetujuan pemilik aset [1].",
        )
        self.assertFalse(is_unsupported_answer(cleaned))

    def test_keeps_pure_unsupported_answer_for_no_citation_guard(self) -> None:
        answer = f"{unsupported_answer_text()} [1]"

        cleaned = crew_main._strip_trailing_unsupported_answer(answer)

        self.assertEqual(cleaned, answer)
        self.assertTrue(is_unsupported_answer(cleaned))

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
            patch("researcher_crew.main._generate_answer", return_value=f"{unsupported_answer_text()} [1]"),
            patch("researcher_crew.main.store_semantic_cache", store_cache),
        ):
            answer, citations, selected_forms, answer_source = crew_main.run_knowledge_crew(
                "Apa saja aturan yang tidak ada di evidence?",
                trace_id="test",
            )

        self.assertEqual(answer, unsupported_answer_text())
        self.assertEqual(citations, [])
        self.assertEqual(selected_forms, [])
        self.assertEqual(answer_source, "fallback")
        store_cache.assert_not_called()


if __name__ == "__main__":
    unittest.main()
