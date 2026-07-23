from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.api.flowchart_service import (  # noqa: E402
    clear_flowchart_cache_for_source,
    find_flowcharts_for_citations,
    get_flowchart_image,
    prune_stale_flowchart_cache,
)


class FlowchartServiceTests(unittest.TestCase):
    def _write_payload(self, directory: Path) -> None:
        payload = {
            "status": "success",
            "source": "SOP Test.pdf",
            "image_page": 4,
            "model": "kiro/auto",
            "result": {
                "title": "Alur Test",
                "confidence": 1.0,
                "text": "Tahapan yang terbaca:\n1. [Start] Mulai\n2. [End] Selesai",
            },
        }
        (directory / "diagram-id.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    def test_returns_diagram_for_matching_flowchart_citation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            cache_dir = root
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "SOP Test.pdf").write_bytes(b"%PDF-1.4\n")
            self._write_payload(cache_dir)

            with patch.dict(os.environ, {"DATA_DIR": str(data_dir)}):
                diagrams = find_flowcharts_for_citations(
                    [
                        {
                            "source": "SOP Test.pdf",
                            "page": 5,
                            "section": "8. ALUR PROSES",
                        }
                    ],
                    cache_dir=cache_dir,
                    model_name="kiro/auto",
                    display_enabled=True,
                )

        self.assertEqual(len(diagrams), 1)
        self.assertEqual(diagrams[0]["id"], "diagram-id")
        self.assertEqual(diagrams[0]["image_url"], "/api/flowcharts/diagram-id")

    def test_ignores_non_flowchart_citation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            cache_dir = root
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "SOP Test.pdf").write_bytes(b"%PDF-1.4\n")
            self._write_payload(cache_dir)

            with patch.dict(os.environ, {"DATA_DIR": str(data_dir)}):
                diagrams = find_flowcharts_for_citations(
                    [
                        {
                            "source": "SOP Test.pdf",
                            "page": 5,
                            "section": "4. KETENTUAN",
                        }
                    ],
                    cache_dir=cache_dir,
                    model_name="kiro/auto",
                    display_enabled=True,
                )

        self.assertEqual(diagrams, [])

    def test_extracts_original_flowchart_image_from_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            cache_dir = root / "flowcharts"
            data_dir = root / "data"
            cache_dir.mkdir()
            data_dir.mkdir()
            flowchart_id = "a" * 64
            source_name = "SOP Test.pdf"

            image_document = fitz.open()
            image_page = image_document.new_page(width=120, height=80)
            image_page.draw_rect(
                fitz.Rect(0, 0, 120, 80),
                color=(0.8, 0.1, 0.1),
                fill=(0.8, 0.1, 0.1),
            )
            pixmap = image_page.get_pixmap()
            image_bytes = pixmap.tobytes("png")
            image_document.close()

            pdf = fitz.open()
            page = pdf.new_page()
            page.insert_image(fitz.Rect(60, 80, 535, 700), stream=image_bytes)
            pdf.save(data_dir / source_name)
            pdf.close()

            (cache_dir / f"{flowchart_id}.json").write_text(
                json.dumps(
                    {
                        "status": "success",
                        "source": source_name,
                        "image_page": 0,
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "FLOWCHART_CACHE_DIR": str(cache_dir),
                    "DATA_DIR": str(data_dir),
                },
            ):
                image = get_flowchart_image(flowchart_id, allow_disabled=True)

        self.assertIsNotNone(image)
        self.assertTrue(image[0].startswith(b"\x89PNG"))
        self.assertEqual(image[1], "image/png")

    def test_ignores_legacy_payload_without_plain_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            cache_dir = root
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "SOP Test.pdf").write_bytes(b"%PDF-1.4\n")
            (cache_dir / "diagram-id.json").write_text(
                json.dumps(
                    {
                        "status": "success",
                        "source": "SOP Test.pdf",
                        "image_page": 4,
                        "model": "kiro/auto",
                        "result": {"title": "Alur", "confidence": 0.9},
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"DATA_DIR": str(data_dir)}):
                diagrams = find_flowcharts_for_citations(
                    [
                        {
                            "source": "SOP Test.pdf",
                            "page": 5,
                            "section": "8. ALUR PROSES",
                        }
                    ],
                    cache_dir=cache_dir,
                    model_name="kiro/auto",
                    display_enabled=True,
                )

        self.assertEqual(diagrams, [])

    def test_ignores_flowchart_when_source_file_has_been_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            cache_dir = root / "flowcharts"
            data_dir = root / "data"
            cache_dir.mkdir()
            data_dir.mkdir()
            self._write_payload(cache_dir)

            with patch.dict(
                os.environ,
                {
                    "FLOWCHART_CACHE_DIR": str(cache_dir),
                    "DATA_DIR": str(data_dir),
                },
            ):
                diagrams = find_flowcharts_for_citations(
                    [
                        {
                            "source": "SOP Test.pdf",
                            "page": 5,
                            "section": "8. ALUR PROSES",
                        }
                    ],
                    cache_dir=cache_dir,
                    model_name="kiro/auto",
                    display_enabled=True,
                )

        self.assertEqual(diagrams, [])

    def test_clear_flowchart_cache_for_source_removes_matching_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            cache_dir = Path(temporary_dir)
            self._write_payload(cache_dir)
            (cache_dir / "other.json").write_text(
                json.dumps(
                    {
                        "status": "success",
                        "source": "SOP Lain.pdf",
                        "image_page": 1,
                        "model": "kiro/auto",
                        "result": {"title": "Alur", "confidence": 1.0, "text": "Tahapan"},
                    }
                ),
                encoding="utf-8",
            )

            removed = clear_flowchart_cache_for_source("SOP Test.pdf", cache_dir=cache_dir)

            self.assertEqual(removed, 1)
            self.assertFalse((cache_dir / "diagram-id.json").exists())
            self.assertTrue((cache_dir / "other.json").exists())

    def test_prune_stale_flowchart_cache_removes_orphan_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            cache_dir = Path(temporary_dir)
            self._write_payload(cache_dir)
            (cache_dir / "active.json").write_text(
                json.dumps(
                    {
                        "status": "success",
                        "source": "SOP Aktif.pdf",
                        "image_page": 1,
                        "model": "kiro/auto",
                        "result": {"title": "Alur", "confidence": 1.0, "text": "Tahapan"},
                    }
                ),
                encoding="utf-8",
            )

            removed = prune_stale_flowchart_cache({"SOP Aktif.pdf"}, cache_dir=cache_dir)

            self.assertEqual(removed, 1)
            self.assertFalse((cache_dir / "diagram-id.json").exists())
            self.assertTrue((cache_dir / "active.json").exists())

    def test_prune_stale_flowchart_cache_keeps_latest_duplicate_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            cache_dir = Path(temporary_dir)
            older = cache_dir / "older.json"
            newer = cache_dir / "newer.json"
            payload = {
                "status": "success",
                "source": "SOP Aktif.pdf",
                "image_page": 4,
                "model": "kiro/auto",
                "result": {"title": "Alur", "confidence": 1.0, "text": "Tahapan"},
            }
            older.write_text(json.dumps(payload), encoding="utf-8")
            newer.write_text(json.dumps(payload), encoding="utf-8")
            os.utime(older, (1, 1))
            os.utime(newer, None)

            removed = prune_stale_flowchart_cache({"SOP Aktif.pdf"}, cache_dir=cache_dir)

            self.assertEqual(removed, 1)
            self.assertFalse(older.exists())
            self.assertTrue(newer.exists())


if __name__ == "__main__":
    unittest.main()
