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

from backend.api.form_schema_generator import (  # noqa: E402
    _schema_prompt,
    delete_schema_for_form_pdf,
    generate_schema_for_form_pdf,
    parse_pdf_for_schema,
)
from backend.api.forms_service import get_form_schema  # noqa: E402


def _write_simple_form(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    page.insert_text((40, 50), "Nama Karyawan:", fontsize=10)
    page.draw_line((130, 52), (260, 52))
    doc.save(path)
    doc.close()


class FormSchemaGeneratorTests(unittest.TestCase):
    def test_parser_extracts_pages_text_and_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            path = Path(temporary_dir) / "Form - Parser Test.pdf"
            _write_simple_form(path)

            parsed = parse_pdf_for_schema(path)

        self.assertEqual(parsed["filename"], "Form - Parser Test.pdf")
        self.assertEqual(parsed["pages"][0]["width"], 300)
        self.assertTrue(any("Nama Karyawan" in line["text"] for line in parsed["text_lines"]))
        self.assertTrue(any(candidate["kind"] == "underline" for candidate in parsed["field_candidates"]))

    def test_prompt_uses_compact_pdf_parse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = Path(temporary_dir)
            path = data_dir / "Form - Compact Prompt.pdf"
            _write_simple_form(path)
            parsed = parse_pdf_for_schema(path)

            with patch.dict(os.environ, {"DATA_DIR": str(data_dir)}):
                prompt = _schema_prompt(path, parsed)

        self.assertLess(len(prompt), 4000)
        self.assertIn('"candidates"', prompt)
        self.assertNotIn('"field_candidates"', prompt)

    def test_generate_schema_writes_valid_model_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            data_dir = root / "data"
            schema_dir = root / "schemas"
            data_dir.mkdir()
            path = data_dir / "Form - Auto Schema.pdf"
            _write_simple_form(path)
            model_output = {
                "title": "Auto Schema",
                "fields": [
                    {
                        "candidate_id": 0,
                        "id": "employee_name",
                        "label": "Nama Karyawan",
                        "type": "text",
                        "required": False,
                        "section": "Informasi Karyawan",
                        "placeholder": "Nama lengkap",
                        "font_size": 10,
                        "clear": True,
                    }
                ],
            }

            with (
                patch.dict(
                    os.environ,
                    {"DATA_DIR": str(data_dir), "FORM_SCHEMA_GROQ_API_KEY": "test-key"},
                ),
                patch(
                    "backend.api.form_schema_generator._call_groq_schema_model",
                    return_value=json.dumps(model_output),
                ),
                patch(
                    "backend.api.form_schema_generator._form_schema_dir",
                    return_value=schema_dir,
                ),
            ):
                result = generate_schema_for_form_pdf(path)

            schema_path = schema_dir / "auto_schema.json"
            payload = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertTrue(result.generated)
        self.assertEqual(result.schema_path, "schemas/auto_schema.json")
        self.assertEqual(payload["path"], "Form - Auto Schema.pdf")
        self.assertEqual(payload["generator"]["source"], "model")
        self.assertEqual(payload["fields"][0]["id"], "employee_name")

    def test_generate_schema_ignores_model_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            data_dir = root / "data"
            schema_dir = root / "schemas"
            data_dir.mkdir()
            path = data_dir / "Form - Compact Schema.pdf"
            _write_simple_form(path)
            model_output = {
                "title": "Compact Schema",
                "fields": [
                    {
                        "i": 0,
                        "id": "employee_name",
                        "l": "Nama Karyawan",
                        "t": "text",
                        "r": [1, 2, 3, 4],
                        "req": True,
                        "s": "Informasi Karyawan",
                        "ph": "Nama lengkap",
                        "fs": 10,
                    }
                ],
            }

            with (
                patch.dict(
                    os.environ,
                    {"DATA_DIR": str(data_dir), "FORM_SCHEMA_GROQ_API_KEY": "test-key"},
                ),
                patch(
                    "backend.api.form_schema_generator._call_groq_schema_model",
                    return_value=json.dumps(model_output),
                ),
                patch(
                    "backend.api.form_schema_generator._form_schema_dir",
                    return_value=schema_dir,
                ),
            ):
                result = generate_schema_for_form_pdf(path)

            payload = json.loads((schema_dir / "compact_schema.json").read_text(encoding="utf-8"))

        self.assertTrue(result.generated)
        self.assertEqual(payload["title"], "Compact Schema")
        self.assertEqual(payload["fields"][0]["label"], "Nama Karyawan")
        self.assertGreater(payload["fields"][0]["rect"]["width"], 100)
        self.assertNotEqual(payload["fields"][0]["rect"]["x"], 1.0)

    def test_generate_schema_falls_back_when_model_candidate_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            data_dir = root / "data"
            schema_dir = root / "schemas"
            data_dir.mkdir()
            path = data_dir / "Form - Bad Rect.pdf"
            _write_simple_form(path)
            model_output = {
                "title": "Bad Rect",
                "fields": [
                    {
                        "candidate_id": 999,
                        "id": "employee_name",
                        "l": "Nama Karyawan",
                        "t": "text",
                    }
                ],
            }

            with (
                patch.dict(
                    os.environ,
                    {"DATA_DIR": str(data_dir), "FORM_SCHEMA_GROQ_API_KEY": "test-key"},
                ),
                patch(
                    "backend.api.form_schema_generator._call_groq_schema_model",
                    return_value=json.dumps(model_output),
                ),
                patch(
                    "backend.api.form_schema_generator._form_schema_dir",
                    return_value=schema_dir,
                ),
            ):
                result = generate_schema_for_form_pdf(path)

            payload = json.loads((schema_dir / "bad_rect.json").read_text(encoding="utf-8"))

        self.assertTrue(result.generated)
        self.assertEqual(payload["generator"]["source"], "heuristic")
        self.assertGreaterEqual(len(payload["fields"]), 1)
        self.assertIn("rect", payload["fields"][0])

    def test_generate_schema_uses_heuristic_without_groq_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            schema_dir = root / "schemas"
            path = root / "Form - No Key.pdf"
            _write_simple_form(path)

            with (
                patch.dict(os.environ, {"FORM_SCHEMA_GROQ_API_KEY": ""}),
                patch(
                    "backend.api.form_schema_generator._form_schema_dir",
                    return_value=schema_dir,
                ),
            ):
                result = generate_schema_for_form_pdf(path)

            payload = json.loads((schema_dir / "no_key.json").read_text(encoding="utf-8"))

        self.assertTrue(result.generated)
        self.assertEqual(payload["generator"]["source"], "heuristic")
        self.assertIn("missing_form_schema_groq_api_key", payload["generator"]["warnings"])

    @unittest.skipUnless(
        (PROJECT_ROOT / "backend" / "data" / "Form - Incident Report (Template).pdf").exists(),
        "Incident Report fixture tidak tersedia",
    )
    def test_incident_report_regenerates_practical_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = PROJECT_ROOT / "backend" / "data"
            schema_dir = Path(temporary_dir) / "schemas"
            path = data_dir / "Form - Incident Report (Template).pdf"

            with (
                patch.dict(os.environ, {"DATA_DIR": str(data_dir), "FORM_SCHEMA_GROQ_API_KEY": ""}),
                patch(
                    "backend.api.form_schema_generator._form_schema_dir",
                    return_value=schema_dir,
                ),
                patch(
                    "backend.api.forms_service._form_schema_dir",
                    return_value=schema_dir,
                ),
            ):
                result = generate_schema_for_form_pdf(path)
                schema = get_form_schema("Form - Incident Report (Template).pdf")

            payload = json.loads((schema_dir / "incident_report.json").read_text(encoding="utf-8"))

        labels = [field["label"] for field in payload["fields"]]
        ids = [field["id"] for field in payload["fields"]]

        self.assertTrue(result.generated)
        self.assertGreaterEqual(len(payload["fields"]), 12)
        self.assertLessEqual(len(payload["fields"]), 20)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(sum(1 for label in labels if label == "Tanggal & Waktu"), 0)
        self.assertIn("Dilaporkan Oleh", labels)
        self.assertIn("Diterima Oleh", labels)
        self.assertIn("Tanggal Laporan", labels)
        self.assertIn("Tanggal Insiden", labels)
        self.assertIn("Jam Insiden", labels)
        self.assertIn("Deskripsi Insiden", labels)
        self.assertIn("Lampiran / Bukti", labels)
        self.assertTrue(any(field["type"] == "textarea" for field in payload["fields"]))
        dilaporkan_oleh = next(field for field in payload["fields"] if field["label"] == "Dilaporkan Oleh")
        self.assertGreater(dilaporkan_oleh["rect"]["width"], 70)
        self.assertGreaterEqual(len(schema["fields"]), 12)

    @unittest.skipUnless(
        (PROJECT_ROOT / "backend" / "data" / "Form - Exit Interview (Template).pdf").exists(),
        "Exit Interview fixture tidak tersedia",
    )
    def test_exit_interview_detects_matrix_inline_and_signatures(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = PROJECT_ROOT / "backend" / "data"
            schema_dir = Path(temporary_dir) / "schemas"
            path = data_dir / "Form - Exit Interview (Template).pdf"

            with (
                patch.dict(os.environ, {"DATA_DIR": str(data_dir), "FORM_SCHEMA_GROQ_API_KEY": ""}),
                patch("backend.api.form_schema_generator._form_schema_dir", return_value=schema_dir),
                patch("backend.api.forms_service._form_schema_dir", return_value=schema_dir),
            ):
                result = generate_schema_for_form_pdf(path)
                schema = get_form_schema("Form - Exit Interview (Template).pdf")

            payload = json.loads((schema_dir / "exit_interview.json").read_text(encoding="utf-8"))

        fields = payload["fields"]
        labels = [field["label"] for field in fields]
        matrix_fields = [
            field
            for field in fields
            if (field.get("layout") or {}).get("kind") == "choice_matrix"
        ]
        signature_fields = [field for field in fields if field["type"] == "signature_image"]
        inline_fields = [
            field
            for field in fields
            if (field.get("layout") or {}).get("kind") == "inline_placeholder"
        ]

        self.assertTrue(result.generated)
        self.assertIn("4. Apakah ada hal yang dapat dilakukan perusahaan untuk mempertahankan Anda?", labels)
        self.assertGreaterEqual(len(matrix_fields), 24)
        self.assertTrue(all(field["type"] == "checkbox" for field in matrix_fields))
        self.assertGreaterEqual(len({field["layout"]["choice_group"] for field in matrix_fields}), 6)
        self.assertEqual(len(signature_fields), 3)
        self.assertGreaterEqual(sum(1 for field in inline_fields if field["label"] == "Nama"), 3)
        self.assertTrue(any((field.get("layout") or {}).get("kind") == "choice_matrix" for field in schema["fields"]))

    @unittest.skipUnless(
        (PROJECT_ROOT / "backend" / "data" / "Form - Onboarding Preparation (Template).pdf").exists(),
        "Onboarding fixture tidak tersedia",
    )
    def test_onboarding_detects_checklist_done_and_dates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = PROJECT_ROOT / "backend" / "data"
            schema_dir = Path(temporary_dir) / "schemas"
            path = data_dir / "Form - Onboarding Preparation (Template).pdf"

            with (
                patch.dict(os.environ, {"DATA_DIR": str(data_dir), "FORM_SCHEMA_GROQ_API_KEY": ""}),
                patch("backend.api.form_schema_generator._form_schema_dir", return_value=schema_dir),
            ):
                result = generate_schema_for_form_pdf(path)

            payload = json.loads((schema_dir / "onboarding_preparation.json").read_text(encoding="utf-8"))

        table_fields = [
            field
            for field in payload["fields"]
            if (field.get("layout") or {}).get("kind") == "table_cell"
        ]
        labels = [field["label"] for field in table_fields]

        self.assertTrue(result.generated)
        self.assertIn("Create User Account - Done", labels)
        self.assertIn("Create User Account - Tanggal", labels)
        self.assertIn("Notebook - Done", labels)
        self.assertGreaterEqual(len(table_fields), 50)
        self.assertTrue(any(field["type"] == "checkbox" for field in table_fields))
        self.assertTrue(any(field["type"] == "date" for field in table_fields))

    @unittest.skipUnless(
        (PROJECT_ROOT / "backend" / "data" / "Form - System Access Control List (Template).pdf").exists(),
        "System Access fixture tidak tersedia",
    )
    def test_system_access_detects_table_cells(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = PROJECT_ROOT / "backend" / "data"
            schema_dir = Path(temporary_dir) / "schemas"
            path = data_dir / "Form - System Access Control List (Template).pdf"

            with (
                patch.dict(os.environ, {"DATA_DIR": str(data_dir), "FORM_SCHEMA_GROQ_API_KEY": ""}),
                patch("backend.api.form_schema_generator._form_schema_dir", return_value=schema_dir),
            ):
                result = generate_schema_for_form_pdf(path)

            payload = json.loads((schema_dir / "system_access_control_list.json").read_text(encoding="utf-8"))

        labels = [field["label"] for field in payload["fields"]]
        table_fields = [
            field
            for field in payload["fields"]
            if (field.get("layout") or {}).get("kind") == "table_cell"
        ]

        self.assertTrue(result.generated)
        self.assertIn("Baris 1 - Nama Karyawan", labels)
        self.assertIn("Baris 1 - Tanggal Pemberian", labels)
        self.assertNotIn("Cloud Console", [field["label"] for field in payload["fields"] if not field.get("layout")])
        self.assertGreaterEqual(len(table_fields), 200)

    def test_delete_schema_for_form_pdf_removes_matching_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            schema_dir = root / "schemas"
            schema_dir.mkdir()
            pdf_path = root / "Form - Delete Me (Template).pdf"
            schema_path = schema_dir / "delete_me.json"
            _write_simple_form(pdf_path)
            schema_path.write_text("{}", encoding="utf-8")

            with patch(
                "backend.api.form_schema_generator._form_schema_dir",
                return_value=schema_dir,
            ):
                result = delete_schema_for_form_pdf(pdf_path)

            exists_after_delete = schema_path.exists()

        self.assertTrue(result.deleted)
        self.assertEqual(result.schema_path, "schemas/delete_me.json")
        self.assertFalse(exists_after_delete)


if __name__ == "__main__":
    unittest.main()
