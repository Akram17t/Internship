from __future__ import annotations

import sys
import types
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

    def test_finalize_answer_citations_merges_citation_only_bullets(self) -> None:
        answer, _ = crew_main._finalize_answer_citations(
            "- Karyawan menulis surat pengunduran diri.\n"
            "- [1]\n"
            "\n"
            "2. Persetujuan Atasan\n"
            "- Jika disetujui, proses berlanjut.\n"
            "• [1]",
            [{"id": 1, "source": "SOP.pdf"}],
        )

        self.assertIn("- Karyawan menulis surat pengunduran diri. [1]", answer)
        self.assertIn("- Jika disetujui, proses berlanjut. [1]", answer)
        self.assertNotIn("- [1]", answer)
        self.assertNotIn("• [1]", answer)

    def test_direct_answer_prompt_reinforces_form_selection_boundaries(self) -> None:
        prompt = crew_main._direct_answer_prompt(
            "Bagaimana alur permohonan hak akses?",
            "[1] Karyawan mengajukan permohonan hak akses dan ACL diperbarui.",
            '[{"name": "Form - Exit Clearance (Template).pdf"}, '
            '{"name": "Form - System Access Control List (Template).pdf"}]',
        )

        self.assertIn("System Access Control List", prompt)
        self.assertIn("Exit Clearance hanya untuk resign/offboarding", prompt)
        self.assertIn("Jangan pilih Exit Clearance hanya karena", prompt)
        self.assertIn("tidak boleh ada baris yang isinya hanya citation", prompt)

    def test_faq_prompt_requests_compact_but_informative_answer(self) -> None:
        with patch(
            "researcher_crew.main._generate_with_model",
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

    def test_generate_with_model_uses_router9_kiro_openai_compatible_payload(self) -> None:
        captured: dict[str, object] = {}

        class FakeCompletions:
            def create(self, **payload: object) -> object:
                captured.update(payload)
                message = types.SimpleNamespace(content="Jawaban dari Kiro [1].")
                choice = types.SimpleNamespace(message=message)
                return types.SimpleNamespace(choices=[choice])

        fake_client = types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=FakeCompletions())
        )
        fake_openai = types.SimpleNamespace(OpenAI=lambda **_: fake_client)

        with (
            patch.dict(
                "os.environ",
                {
                    "MODEL": "kiro/auto",
                    "CHAT_BASE_URL": "http://localhost:20128/v1",
                    "CHAT_API_KEY": "test-key",
                    "CHAT_TIMEOUT_SECONDS": "240",
                },
                clear=True,
            ),
            patch.dict(sys.modules, {"openai": fake_openai}),
        ):
            answer = crew_main._generate_with_model(
                "Halo",
                num_predict=64,
                temperature=0.0,
                seed=11,
            )

        self.assertEqual(answer, "Jawaban dari Kiro [1].")
        self.assertEqual(captured["model"], "kiro/auto")
        self.assertEqual(captured["max_tokens"], 64)
        self.assertNotIn("reasoning_effort", captured)
        self.assertNotIn("seed", captured)

    def test_generate_answer_sends_role_prompt_as_system_message(self) -> None:
        with patch(
            "researcher_crew.main._generate_with_model",
            return_value="Jawaban bersumber [1].",
        ) as generate:
            answer = crew_main._generate_answer(
                "Bagaimana alur permohonan hak akses?",
                "[1] Karyawan mengajukan permohonan hak akses.",
                '[{"name": "Form - System Access Control List (Template).pdf"}]',
            )

        user_prompt = generate.call_args.args[0]
        self.assertEqual(answer, "Jawaban bersumber [1].")
        self.assertEqual(generate.call_args.kwargs["system_prompt"], crew_main.ANSWER_ROLE_PROMPT)
        self.assertNotIn(crew_main.ANSWER_ROLE_PROMPT, user_prompt)
        self.assertIn("Pertanyaan terbaru:", user_prompt)
        self.assertIn("Retrieved evidence:", user_prompt)
        self.assertIn("Available downloadable forms:", user_prompt)
        self.assertIn(crew_main.ANSWER_TASK_RULES, user_prompt)

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

    def test_form_selection_removes_visible_used_form_heading(self) -> None:
        answer = (
            "Alur exit clearance dijalankan pada hari terakhir bekerja [1].\n\n"
            "**Form yang digunakan**\n\n"
            'FORM_SELECTION: ["Form - Exit Clearance (Template).pdf"]'
        )

        cleaned, selected_forms = crew_main._split_form_selection(answer)

        self.assertEqual(
            cleaned,
            "Alur exit clearance dijalankan pada hari terakhir bekerja [1].",
        )
        self.assertEqual(selected_forms, ["Form - Exit Clearance (Template).pdf"])

    def test_cached_answer_visible_form_heading_can_be_stripped(self) -> None:
        cleaned = crew_main._strip_visible_form_download_copy(
            "Alur exit clearance dijalankan pada hari terakhir bekerja [1].\n\n"
            "Form yang digunakan"
        )

        self.assertEqual(
            cleaned,
            "Alur exit clearance dijalankan pada hari terakhir bekerja [1].",
        )

    def test_rewrite_keeps_original_when_ai_says_keep(self) -> None:
        with patch(
            "researcher_crew.main._generate_with_model",
            return_value="KEEP",
        ) as generate:
            rewritten = crew_main._rewrite_query(
                "HRIS tuh apa sih?",
                "Percakapan sebelumnya yang panjang.",
            )

        self.assertEqual(rewritten, "HRIS tuh apa sih?")
        generate.assert_called_once()

    def test_rewrite_prompt_handles_recent_case_reference(self) -> None:
        with patch(
            "researcher_crew.main._generate_with_model",
            return_value=(
                "REWRITE: Kalau perjalanan dinas ke Bali selama 11 hari, "
                "uang makan dan uang sakunya dihitung per hari atau gimana?"
            ),
        ) as generate:
            rewritten = crew_main._rewrite_query(
                "Kalau kasus barusan, uang makan dan uang sakunya itu dihitung per hari atau gimana?",
                "Percakapan membahas perjalanan dinas ke Bali selama 11 hari.",
            )

        prompt = generate.call_args.args[0]
        self.assertIn("kasus barusan", prompt)
        self.assertIn(
            "Kalau kasus barusan, uang makan dan uang sakunya itu dihitung per hari atau gimana?",
            prompt,
        )
        self.assertEqual(
            rewritten,
            "Kalau perjalanan dinas ke Bali selama 11 hari, uang makan dan uang sakunya dihitung per hari atau gimana?",
        )
        generate.assert_called_once()

    def test_rewrite_uses_llm_for_explicit_context_reference(self) -> None:
        with patch(
            "researcher_crew.main._generate_with_model",
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

    def test_rewrite_ignores_forced_reference_reasoning_without_rewrite_line(self) -> None:
        with patch(
            "researcher_crew.main._generate_with_model",
            return_value=(
                "Okay, let's see. The user is asking about the previous case. "
                "I need to make this standalone."
            ),
        ):
            rewritten = crew_main._rewrite_query(
                "Dari kasus tadi, uang makan dan uang sakunya itu dihitung per hari atau langsung total?",
                "Percakapan membahas perjalanan dinas Manager ke luar negeri selama 3 hari.",
            )

        self.assertEqual(
            rewritten,
            "Dari kasus tadi, uang makan dan uang sakunya itu dihitung per hari atau langsung total?",
        )

    def test_rewrite_extracts_rewrite_line_after_extra_text(self) -> None:
        with patch(
            "researcher_crew.main._generate_with_model",
            return_value=(
                "Saya akan membuat pertanyaan mandiri.\n"
                "REWRITE: Untuk perjalanan dinas Manager ke luar negeri selama 3 hari, "
                "uang makan dan uang sakunya dihitung per hari atau langsung total?"
            ),
        ):
            rewritten = crew_main._rewrite_query(
                "Dari kasus tadi, uang makan dan uang sakunya itu dihitung per hari atau langsung total?",
                "Percakapan membahas perjalanan dinas Manager ke luar negeri selama 3 hari.",
            )

        self.assertEqual(
            rewritten,
            "Untuk perjalanan dinas Manager ke luar negeri selama 3 hari, "
            "uang makan dan uang sakunya dihitung per hari atau langsung total?",
        )

    def test_rewrite_supports_implicit_context_reference(self) -> None:
        with patch(
            "researcher_crew.main._generate_with_model",
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
            "researcher_crew.main._generate_with_model",
            return_value="HRIS itu apa sih?",
        ):
            rewritten = crew_main._rewrite_query(
                "HRIS tuh apa sih?",
                "Percakapan membahas resign.",
            )

        self.assertEqual(rewritten, "HRIS tuh apa sih?")

    def test_rewrite_accepts_ai_rewrite_without_extra_guard(self) -> None:
        with patch(
            "researcher_crew.main._generate_with_model",
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
            "Kalau gue mau perjalanan dinas, alur yang harus dijalani gimana?",
        )
        generate.assert_called_once()

    def test_rewrite_accepts_ai_context_addition(self) -> None:
        with patch(
            "researcher_crew.main._generate_with_model",
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
            "Jelasin juga batasan sharing data itu sampai mana "
            "dalam konteks administrasi karyawan baru",
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
