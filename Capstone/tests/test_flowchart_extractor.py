from __future__ import annotations

import sys
import unittest
from pathlib import Path

from langchain_core.documents import Document

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.preprocessing.chunker import chunk_documents  # noqa: E402
from backend.preprocessing.flowchart_extractor import (  # noqa: E402
    _find_dangling_edge_candidate,
    _find_graph_issues,
    _linearize_flowchart,
    _validate_result,
    detect_flowchart_candidates,
)


class FlowchartExtractorTests(unittest.TestCase):
    def test_detector_supports_diagram_on_following_page(self) -> None:
        candidates = detect_flowchart_candidates(
            [
                "8. DOKUMEN TERKAIT\n9. ALUR PROSES\nDiagram berikut menggambarkan alur.",
                "STANDARD OPERATING PROCEDURE\n9 dari 9",
            ],
            [0.0, 0.25],
            min_image_area_ratio=0.08,
            max_continuation_pages=1,
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].heading_page, 0)
        self.assertEqual(candidates[0].image_page, 1)
        self.assertEqual(candidates[0].section, "9. ALUR PROSES")

    def test_detector_ignores_large_images_without_flowchart_heading(self) -> None:
        candidates = detect_flowchart_candidates(
            ["1. TUJUAN", "2. RUANG LINGKUP"],
            [0.4, 0.5],
            min_image_area_ratio=0.08,
        )

        self.assertEqual(candidates, [])

    def test_validation_drops_edges_to_unknown_nodes(self) -> None:
        result = _validate_result(
            {
                "title": "Alur Test",
                "confidence": 0.9,
                "nodes": [
                    {"id": "n1", "type": "start", "text": "Mulai", "confidence": 1},
                    {"id": "n2", "type": "process", "text": "Proses", "confidence": 0.9},
                ],
                "edges": [
                    {"from": "n1", "to": "n2", "label": "", "confidence": 0.9},
                    {"from": "n2", "to": "missing", "label": "", "confidence": 0.2},
                ],
            }
        )

        self.assertEqual(len(result["edges"]), 1)

    def test_linearized_flowchart_keeps_branch_labels(self) -> None:
        result = _validate_result(
            {
                "title": "Alur Persetujuan",
                "confidence": 0.95,
                "nodes": [
                    {"id": "n1", "type": "decision", "text": "Disetujui?", "confidence": 1},
                    {"id": "n2", "type": "process", "text": "Ulangi pengajuan", "confidence": 1},
                ],
                "edges": [
                    {"from": "n1", "to": "n2", "label": "Tidak", "confidence": 1},
                ],
            }
        )

        content = _linearize_flowchart("8. ALUR PROSES", result)

        self.assertIn("Disetujui? --Tidak--> Ulangi pengajuan", content)

    def test_graph_validation_detects_disconnected_end(self) -> None:
        result = _validate_result(
            {
                "title": "Alur Test",
                "confidence": 0.9,
                "nodes": [
                    {"id": "n1", "type": "start", "text": "Mulai", "confidence": 1},
                    {"id": "n2", "type": "process", "text": "Proses", "confidence": 1},
                    {"id": "n3", "type": "end", "text": "Selesai", "confidence": 1},
                ],
                "edges": [
                    {"from": "n1", "to": "n2", "label": "", "confidence": 1},
                ],
            }
        )

        issues = _find_graph_issues(result)

        self.assertTrue(any("Proses" in issue and "panah keluar" in issue for issue in issues))
        self.assertTrue(any("Selesai" in issue and "panah masuk" in issue for issue in issues))

    def test_finds_single_dangling_edge_candidate(self) -> None:
        result = _validate_result(
            {
                "title": "Alur Test",
                "confidence": 0.9,
                "nodes": [
                    {"id": "n1", "type": "start", "text": "Mulai", "confidence": 1},
                    {"id": "n2", "type": "process", "text": "Proses", "confidence": 1},
                    {"id": "n3", "type": "end", "text": "Selesai", "confidence": 1},
                ],
                "edges": [
                    {"from": "n1", "to": "n2", "label": "", "confidence": 1},
                ],
            }
        )

        candidate = _find_dangling_edge_candidate(result)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate[0]["text"], "Proses")
        self.assertEqual(candidate[1]["text"], "Selesai")

    def test_flowchart_is_one_chunk_and_replaces_native_placeholder(self) -> None:
        native_document = Document(
            page_content=(
                "8. ALUR PROSES\n"
                "Diagram berikut menggambarkan alur proses kontrol akses."
            ),
            metadata={
                "source": "SOP Test.pdf",
                "page": 7,
                "document_kind": "sop",
            },
        )
        flowchart_document = Document(
            page_content=(
                "8. ALUR PROSES\nAlur Kontrol Akses\n\nTahapan yang terbaca:\n"
                + "\n".join(f"{index}. [Process] Langkah {index}" for index in range(1, 150))
            ),
            metadata={
                "source": "SOP Test.pdf",
                "page": 8,
                "document_kind": "sop",
                "section": "8. ALUR PROSES",
                "content_type": "flowchart",
                "extraction_method": "ollama_vision",
            },
        )

        chunks = chunk_documents([native_document, flowchart_document])

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].metadata["content_type"], "flowchart")
        self.assertIn("Langkah 149", chunks[0].page_content)

    def test_low_confidence_flowchart_is_not_embedded(self) -> None:
        documents = [
            Document(
                page_content="8. ALUR PROSES\nDiagram berikut menggambarkan alur.",
                metadata={
                    "source": "SOP Test.pdf",
                    "page": 7,
                    "document_kind": "sop",
                },
            ),
            Document(
                page_content="8. ALUR PROSES\nHasil visual meragukan",
                metadata={
                    "source": "SOP Test.pdf",
                    "page": 8,
                    "document_kind": "sop",
                    "section": "8. ALUR PROSES",
                    "content_type": "flowchart",
                    "anomaly": "flowchart_low_confidence",
                },
            ),
        ]

        chunks = chunk_documents(documents)

        self.assertEqual(len(chunks), 1)
        self.assertNotEqual(chunks[0].metadata.get("content_type"), "flowchart")
        self.assertNotIn("Hasil visual meragukan", chunks[0].page_content)

    def test_incomplete_graph_is_not_embedded(self) -> None:
        documents = [
            Document(
                page_content="8. ALUR PROSES\nDiagram berikut menggambarkan alur.",
                metadata={
                    "source": "SOP Test.pdf",
                    "page": 7,
                    "document_kind": "sop",
                },
            ),
            Document(
                page_content="8. ALUR PROSES\nSelesai tidak tersambung",
                metadata={
                    "source": "SOP Test.pdf",
                    "page": 8,
                    "document_kind": "sop",
                    "section": "8. ALUR PROSES",
                    "content_type": "flowchart",
                    "anomaly": "flowchart_incomplete_graph",
                },
            ),
        ]

        chunks = chunk_documents(documents)

        self.assertEqual(len(chunks), 1)
        self.assertNotIn("Selesai tidak tersambung", chunks[0].page_content)


if __name__ == "__main__":
    unittest.main()
