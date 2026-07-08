from __future__ import annotations

import sys
import unittest
from pathlib import Path

from langchain_core.documents import Document

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.preprocessing.chunker import (  # noqa: E402
    _looks_like_heading,
    chunk_documents,
    prepare_documents_for_chunking,
    split_documents_by_section,
)


class ChunkerTests(unittest.TestCase):
    def test_heading_detection_rejects_steps_and_table_rows(self) -> None:
        self.assertTrue(_looks_like_heading("1. TUJUAN"))
        self.assertTrue(_looks_like_heading("4. KETENTUAN"))
        self.assertTrue(_looks_like_heading("4.1 Prinsip Umum"))
        self.assertTrue(_looks_like_heading("4.2.1 Identifikasi dan Otentikasi"))

        self.assertFalse(_looks_like_heading("1. Requestor mengisi Form Permohonan"))
        self.assertFalse(_looks_like_heading("2. Pengguna meminta persetujuan pemilik aset"))
        self.assertFalse(_looks_like_heading("1 Menginput data karyawan baru HR Personnel Staff"))
        self.assertFalse(_looks_like_heading("PKWT/PKWTT"))

    def test_repeated_section_segments_are_merged_with_page_end(self) -> None:
        documents = [
            Document(
                page_content="5. TUGAS DAN TANGGUNG JAWAB\nPeran Tanggung Jawab",
                metadata={"source": "SOP Test.pdf", "page": 4},
            ),
            Document(
                page_content=(
                    "Karyawan terkait mengisi form dan menyerahkan dokumen pendukung.\n"
                    "Atasan terkait mereview form dan memberikan persetujuan."
                ),
                metadata={"source": "SOP Test.pdf", "page": 5},
            ),
        ]

        prepared = prepare_documents_for_chunking(documents)

        self.assertEqual(len(prepared), 1)
        self.assertEqual(prepared[0].metadata["section"], "5. TUGAS DAN TANGGUNG JAWAB")
        self.assertEqual(prepared[0].metadata["page"], 4)
        self.assertEqual(prepared[0].metadata["page_end"], 5)
        self.assertIn("Karyawan terkait mengisi form", prepared[0].page_content)

    def test_table_chunks_keep_header_context(self) -> None:
        repeated_rows = "\n".join(
            f"Dalam Negeri Manager Rp {150000 + index}.000 Rp 125.000 Rp 80.000"
            for index in range(80)
        )
        documents = [
            Document(
                page_content=(
                    "4.7 Uang Saku dan Uang Makan Harian\n"
                    "Destinasi Jabatan Uang Makan (per hari)\n"
                    "Uang Saku s.d. hari ke-8\n"
                    "Uang Saku hari ke-9 dst."
                ),
                metadata={"source": "SOP Test.pdf", "page": 5},
            ),
            Document(
                page_content=repeated_rows,
                metadata={"source": "SOP Test.pdf", "page": 6},
            ),
        ]

        chunks = chunk_documents(documents)
        money_chunks = [chunk for chunk in chunks if "Rp " in chunk.page_content]

        self.assertGreater(len(money_chunks), 1)
        self.assertTrue(
            all("Destinasi Jabatan Uang Makan" in chunk.page_content for chunk in money_chunks)
        )

    def test_orphan_policy_line_is_not_left_in_activity_section(self) -> None:
        documents = [
            Document(
                page_content=(
                    "4.8 Ketentuan Lain\n"
                    "• Perjalanan luar negeri mengikuti kurs TT counter.\n"
                    "5. TUGAS DAN TANGGUNG JAWAB\n"
                    "Peran Tanggung Jawab\n"
                    "6. AKTIVITAS\n"
                    "1. Requestor mengisi Form Permohonan.\n"
                    "Perjalanan dinas lebih dari 12 hari kerja berturut-turut dianggap penugasan"
                ),
                metadata={"source": "SOP Test.pdf", "page": 6},
            )
        ]

        sections = split_documents_by_section(documents)
        activity_text = "\n".join(
            section.page_content
            for section in sections
            if section.metadata.get("section") == "6. AKTIVITAS"
        )
        relocated = [
            section
            for section in sections
            if section.metadata.get("anomaly") == "orphan_policy_line_relocated"
        ]

        self.assertNotIn("Perjalanan dinas lebih dari 12", activity_text)
        self.assertEqual(len(relocated), 1)
        self.assertEqual(relocated[0].metadata["section"], "4.8 Ketentuan Lain")


if __name__ == "__main__":
    unittest.main()
