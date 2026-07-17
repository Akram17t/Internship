from __future__ import annotations

import base64
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.api.main import app  # noqa: E402


def _b64(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


def _auth_ok(_authorization: str = "") -> str:
    return "admin@example.com"


class FormTemplateDownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_guest_can_download_form_pdf_template(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = Path(temporary_dir)
            source = data_dir / "Form - Guest Access.pdf"
            source.write_bytes(b"%PDF-1.4\n% form fixture\n")

            with patch.dict(os.environ, {"DATA_DIR": str(data_dir)}):
                response = self.client.get(f"/api/documents/{quote(source.name, safe='')}")

        self.assertEqual(response.status_code, 200)
        self.assertIn("application/pdf", response.headers["content-type"])
        self.assertEqual(response.content, b"%PDF-1.4\n% form fixture\n")

    def test_guest_can_download_existing_docx_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = Path(temporary_dir)
            pdf_path = data_dir / "Form - Guest Access.pdf"
            docx_path = data_dir / "Form - Guest Access.docx"
            pdf_path.write_bytes(b"%PDF-1.4\n% form fixture\n")
            docx_path.write_bytes(b"docx fixture")

            with patch.dict(os.environ, {"DATA_DIR": str(data_dir)}):
                response = self.client.get(
                    f"/api/documents/{quote(pdf_path.name, safe='')}?format=docx",
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["content-type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertEqual(response.content, b"docx fixture")

    def test_formfill_endpoints_are_removed(self) -> None:
        self.assertEqual(self.client.get("/api/forms/fields", params={"path": "x"}).status_code, 404)
        self.assertEqual(self.client.get("/api/forms/schema", params={"path": "x"}).status_code, 404)
        self.assertEqual(self.client.post("/api/forms/fill", json={}).status_code, 404)

    def test_admin_insert_form_pdf_creates_docx_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = Path(temporary_dir)

            def fake_ensure(pdf_path: Path, *, replace: bool = False) -> Path:
                docx_path = pdf_path.with_suffix(".docx")
                docx_path.write_bytes(b"generated:" + pdf_path.read_bytes())
                return docx_path

            with (
                patch.dict(os.environ, {"DATA_DIR": str(data_dir)}),
                patch("backend.api.routes_admin._require_admin", side_effect=_auth_ok),
                patch("backend.api.routes_admin.ensure_form_docx_template", side_effect=fake_ensure),
            ):
                response = self.client.post(
                    "/api/admin/documents",
                    json={
                        "filename": "Form - Insert Test.pdf",
                        "content_base64": _b64(b"%PDF-1.4\ninsert\n"),
                    },
                )

            docx_path = data_dir / "Form - Insert Test.docx"
            docx_exists = docx_path.exists()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(docx_exists)
        self.assertTrue(response.json()["item"]["relative_path"].endswith(".pdf"))

    def test_admin_update_form_pdf_replaces_docx_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = Path(temporary_dir)
            pdf_path = data_dir / "Form - Update Test.pdf"
            docx_path = data_dir / "Form - Update Test.docx"
            pdf_path.write_bytes(b"%PDF-1.4\nold\n")
            docx_path.write_bytes(b"old docx")
            calls: list[bool] = []

            def fake_ensure(path: Path, *, replace: bool = False) -> Path:
                calls.append(replace)
                next_docx = path.with_suffix(".docx")
                next_docx.write_bytes(b"new docx")
                return next_docx

            with (
                patch.dict(os.environ, {"DATA_DIR": str(data_dir)}),
                patch("backend.api.routes_admin._require_admin", side_effect=_auth_ok),
                patch("backend.api.routes_admin.ensure_form_docx_template", side_effect=fake_ensure),
            ):
                response = self.client.post(
                    "/api/admin/documents",
                    json={
                        "filename": pdf_path.name,
                        "content_base64": _b64(b"%PDF-1.4\nnew\n"),
                        "replace_path": pdf_path.name,
                    },
                )

            next_content = docx_path.read_bytes()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(next_content, b"new docx")
        self.assertEqual(calls, [True])

    def test_admin_delete_form_pdf_deletes_docx_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = Path(temporary_dir)
            pdf_path = data_dir / "Form - Delete Test.pdf"
            docx_path = data_dir / "Form - Delete Test.docx"
            pdf_path.write_bytes(b"%PDF-1.4\nold\n")
            docx_path.write_bytes(b"old docx")

            with (
                patch.dict(os.environ, {"DATA_DIR": str(data_dir)}),
                patch("backend.api.routes_admin._require_admin", side_effect=_auth_ok),
            ):
                response = self.client.delete(
                    f"/api/admin/documents/{quote(pdf_path.name, safe='')}",
                )

            pdf_exists = pdf_path.exists()
            docx_exists = docx_path.exists()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(pdf_exists)
        self.assertFalse(docx_exists)

    def test_admin_rejects_form_docx_upload_as_primary_document(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = Path(temporary_dir)

            with (
                patch.dict(os.environ, {"DATA_DIR": str(data_dir)}),
                patch("backend.api.routes_admin._require_admin", side_effect=_auth_ok),
            ):
                response = self.client.post(
                    "/api/admin/documents",
                    json={
                        "filename": "Form - Manual Word.docx",
                        "content_base64": _b64(b"docx"),
                    },
                )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Upload form Word tidak didukung", response.json()["detail"])

    def test_library_hides_form_docx_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = Path(temporary_dir)
            (data_dir / "Form - Library Test.pdf").write_bytes(b"%PDF-1.4\n")
            (data_dir / "Form - Library Test.docx").write_bytes(b"docx")
            (data_dir / "SOP - Visible.docx").write_bytes(b"docx")

            with (
                patch.dict(os.environ, {"DATA_DIR": str(data_dir)}),
                patch("backend.api.routes_admin._require_admin", side_effect=_auth_ok),
            ):
                response = self.client.get("/api/library")

        self.assertEqual(response.status_code, 200)
        names = [item["name"] for item in response.json()]
        self.assertIn("Form - Library Test.pdf", names)
        self.assertIn("SOP - Visible.docx", names)
        self.assertNotIn("Form - Library Test.docx", names)


class FormfillRemovalStaticTests(unittest.TestCase):
    def test_frontend_has_no_formfill_ui_references(self) -> None:
        frontend_files = [
            PROJECT_ROOT / "frontend" / "web" / "index.html",
            PROJECT_ROOT / "frontend" / "web" / "assets" / "app.js",
            PROJECT_ROOT / "frontend" / "web" / "assets" / "styles.css",
            PROJECT_ROOT / "frontend" / "web" / "assets" / "js" / "auth.js",
            PROJECT_ROOT / "frontend" / "web" / "assets" / "js" / "chat.js",
            PROJECT_ROOT / "frontend" / "web" / "assets" / "js" / "library.js",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in frontend_files)

        for forbidden in [
            "FormEditor",
            "formFill",
            "formDraft",
            "form-fill",
            "form-editor",
            "form-preview",
            "Isi & download",
            "Download form terisi",
            "Draft tersimpan",
            "/api/forms",
        ]:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, combined)

        self.assertIn("Download template", combined)
        self.assertIn("withDownloadFormat(pending.url, \"docx\")", combined)


if __name__ == "__main__":
    unittest.main()
