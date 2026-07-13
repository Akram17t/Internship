from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.api.forms_service import fill_schema_form  # noqa: E402
from backend.api.main import app  # noqa: E402


TARGET_FORM_PATH = "Form - Perjalanan Dinas - Penyelesaian (Template).pdf"
OTHER_FORM_PATH = "Form - Exit Interview (Template).pdf"


def _sample_png_bytes() -> bytes:
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.Rect(0, 0, 20, 10), False)
    pixmap.clear_with(0xFFFFFF)
    return pixmap.tobytes("png")


PNG_BYTES = _sample_png_bytes()


class FormSchemaRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def _valid_values(self) -> dict[str, str]:
        return {
            "division": "Finance",
            "employee_name": "Akram",
            "position": "Staff",
            "destination": "Bandung",
            "duration": "2 hari, 10-11 Juli 2026",
            "total_amount": "1500000",
        }

    def test_schema_endpoint_returns_target_schema(self) -> None:
        response = self.client.get("/api/forms/schema", params={"path": TARGET_FORM_PATH})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["path"], TARGET_FORM_PATH)
        self.assertEqual(payload["pages"][0]["width"], 612)
        self.assertTrue(any(field["id"] == "applicant_signature" for field in payload["fields"]))
        division_field = next(field for field in payload["fields"] if field["id"] == "division")
        self.assertTrue(division_field["clear"])
        self.assertGreaterEqual(division_field["clear_padding"], 0)

    def test_schema_endpoint_404_for_form_without_schema(self) -> None:
        response = self.client.get("/api/forms/schema", params={"path": OTHER_FORM_PATH})

        self.assertEqual(response.status_code, 404)

    def test_fill_endpoint_rejects_unknown_schema_field(self) -> None:
        response = self.client.post(
            "/api/forms/fill",
            json={
                "path": TARGET_FORM_PATH,
                "values": {**self._valid_values(), "bogus_field": "x"},
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("tidak dikenal", response.json()["detail"])

    def test_fill_endpoint_allows_missing_form_values(self) -> None:
        response = self.client.post(
            "/api/forms/fill",
            json={
                "path": TARGET_FORM_PATH,
                "values": {"division": "Finance"},
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")

    def test_fill_endpoint_rejects_non_image_signature_upload(self) -> None:
        payload = {"path": TARGET_FORM_PATH, "values": self._valid_values()}
        response = self.client.post(
            "/api/forms/fill",
            data={"payload": json.dumps(payload)},
            files={"applicant_signature": ("signature.txt", io.BytesIO(b"not-image"), "text/plain")},
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("PNG atau JPEG", response.json()["detail"])

    def test_fill_endpoint_returns_pdf_for_schema_form(self) -> None:
        values = {
            **self._valid_values(),
            "hotel_detail": "2 malam @ Rp 500.000 x 1 kamar",
            "hotel_amount": "1000000",
            "applicant_name": "Akram",
            "applicant_role": "Staff",
        }
        payload = {"path": TARGET_FORM_PATH, "values": values}

        response = self.client.post(
            "/api/forms/fill",
            data={"payload": json.dumps(payload)},
            files={"applicant_signature": ("signature.png", io.BytesIO(PNG_BYTES), "image/png")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertIn("attachment;", response.headers["content-disposition"])

        with fitz.open(stream=response.content, filetype="pdf") as doc:
            text = doc[0].get_text()
            self.assertIn("Finance", text)
            self.assertIn("Akram", text)
            self.assertGreater(len(doc[0].get_images(full=True)), 0)


class SchemaRenderUnitTests(unittest.TestCase):
    def test_fill_schema_form_supports_textarea_checkbox_and_signature(self) -> None:
        schema = {
            "path": "test.pdf",
            "title": "Synthetic",
            "pages": [{"number": 0, "width": 200.0, "height": 200.0}],
            "fields": [
                {
                    "id": "notes",
                    "label": "Catatan",
                    "type": "textarea",
                    "page": 0,
                    "rect": {"x": 20.0, "y": 20.0, "width": 120.0, "height": 40.0},
                    "required": False,
                    "section": "Test",
                    "placeholder": None,
                    "font_size": 10.0,
                    "align": "left",
                    "line_height": 1.08,
                    "clear": True,
                    "clear_padding": 1.0,
                },
                {
                    "id": "approved",
                    "label": "Setuju",
                    "type": "checkbox",
                    "page": 0,
                    "rect": {"x": 20.0, "y": 80.0, "width": 26.0, "height": 18.0},
                    "required": False,
                    "section": "Test",
                    "placeholder": None,
                    "font_size": 10.0,
                    "align": "center",
                    "line_height": 1.0,
                    "clear": True,
                    "clear_padding": 1.0,
                },
                {
                    "id": "signature",
                    "label": "Signature",
                    "type": "signature_image",
                    "page": 0,
                    "rect": {"x": 20.0, "y": 110.0, "width": 40.0, "height": 24.0},
                    "required": False,
                    "section": "Test",
                    "placeholder": None,
                    "font_size": 10.0,
                    "align": "left",
                    "line_height": 1.0,
                    "clear": True,
                    "clear_padding": 1.0,
                },
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "test.pdf"
            doc = fitz.open()
            doc.new_page(width=200, height=200)
            doc.save(path)
            doc.close()

            with patch("backend.api.forms_service._schema_for_resolved_path", return_value=schema):
                content = fill_schema_form(
                    path,
                    {"notes": "Baris pertama\nBaris kedua", "approved": True},
                    {
                        "signature": {
                            "filename": "signature.png",
                            "content_type": "image/png",
                            "content": PNG_BYTES,
                        }
                    },
                )

        with fitz.open(stream=content, filetype="pdf") as rendered:
            page = rendered[0]
            text = page.get_text()
            self.assertIn("Baris pertama", text)
            self.assertIn("X", text)
            self.assertGreater(len(page.get_images(full=True)), 0)


if __name__ == "__main__":
    unittest.main()
