from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.api.flowchart_service import find_flowcharts_for_citations  # noqa: E402


class FlowchartServiceTests(unittest.TestCase):
    def _write_payload(
        self,
        directory: Path,
        *,
        graph_issues: list[str] | None = None,
    ) -> None:
        payload = {
            "status": "success",
            "source": "SOP Test.pdf",
            "image_page": 4,
            "model": "qwen3.5:9b",
            "graph_issues": graph_issues or [],
            "result": {
                "title": "Alur Test",
                "confidence": 0.95,
                "nodes": [
                    {
                        "id": "n1",
                        "type": "start",
                        "text": "Mulai",
                        "confidence": 1,
                    },
                    {
                        "id": "n2",
                        "type": "end",
                        "text": "Selesai",
                        "confidence": 1,
                    },
                ],
                "edges": [
                    {
                        "from": "n1",
                        "to": "n2",
                        "label": "",
                        "confidence": 1,
                    }
                ],
            },
        }
        (directory / "diagram-id.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    def test_returns_diagram_for_matching_flowchart_citation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            cache_dir = Path(temporary_dir)
            self._write_payload(cache_dir)

            diagrams = find_flowcharts_for_citations(
                [
                    {
                        "source": "SOP Test.pdf",
                        "page": 5,
                        "section": "8. ALUR PROSES",
                    }
                ],
                cache_dir=cache_dir,
                model_name="qwen3.5:9b",
            )

        self.assertEqual(len(diagrams), 1)
        self.assertEqual(diagrams[0]["id"], "diagram-id")
        self.assertEqual(diagrams[0]["edges"][0]["source"], "n1")
        self.assertEqual(diagrams[0]["edges"][0]["target"], "n2")

    def test_ignores_non_flowchart_citation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            cache_dir = Path(temporary_dir)
            self._write_payload(cache_dir)

            diagrams = find_flowcharts_for_citations(
                [
                    {
                        "source": "SOP Test.pdf",
                        "page": 5,
                        "section": "4. KETENTUAN",
                    }
                ],
                cache_dir=cache_dir,
                model_name="qwen3.5:9b",
            )

        self.assertEqual(diagrams, [])

    def test_ignores_payload_with_graph_anomaly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            cache_dir = Path(temporary_dir)
            self._write_payload(cache_dir, graph_issues=["Node end terputus"])

            diagrams = find_flowcharts_for_citations(
                [
                    {
                        "source": "SOP Test.pdf",
                        "page": 5,
                        "section": "8. ALUR PROSES",
                    }
                ],
                cache_dir=cache_dir,
                model_name="qwen3.5:9b",
            )

        self.assertEqual(diagrams, [])


if __name__ == "__main__":
    unittest.main()
