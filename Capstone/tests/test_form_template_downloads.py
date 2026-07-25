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
from backend.api.storage import (  # noqa: E402
    _iter_form_downloads,
    _related_form_downloads_for_citations,
)


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

    def test_public_config_disables_typing_animation_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            response = self.client.get("/api/config")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["typing_animation_enabled"])

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

    def test_admin_delete_parent_document_deletes_linked_forms(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = Path(temporary_dir)
            sop_path = data_dir / "SOP - Manual.pdf"
            sop_path.write_bytes(b"%PDF-1.4\n")
            form_dir = data_dir / "forms" / "manual"
            form_dir.mkdir(parents=True)
            (form_dir / "Checklist.xlsx").write_bytes(b"xlsx")
            (form_dir / "Checklist.docx").write_bytes(b"docx")

            with (
                patch.dict(os.environ, {"DATA_DIR": str(data_dir)}),
                patch("backend.api.routes_admin._require_admin", side_effect=_auth_ok),
            ):
                response = self.client.delete(
                    f"/api/admin/documents/{quote(sop_path.name, safe='')}",
                )

            sop_exists = sop_path.exists()
            form_dir_exists = form_dir.exists()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(sop_exists)
        self.assertFalse(form_dir_exists)

    def test_admin_accepts_form_docx_upload_without_form_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = Path(temporary_dir)
            sop_path = data_dir / "SOP - Manual.docx"
            sop_path.write_bytes(b"docx sop")

            with (
                patch.dict(os.environ, {"DATA_DIR": str(data_dir)}),
                patch("backend.api.routes_admin._require_admin", side_effect=_auth_ok),
            ):
                response = self.client.post(
                    "/api/admin/documents",
                    json={
                        "filename": "Manual Word.docx",
                        "content_base64": _b64(b"docx"),
                        "document_kind": "form",
                        "linked_sop_path": sop_path.name,
                    },
                )

        self.assertEqual(response.status_code, 200)
        item = response.json()["item"]
        self.assertEqual(item["document_kind"], "form")
        self.assertEqual(item["doc_type"], "docx")
        self.assertEqual(item["formats"], ["docx"])
        self.assertTrue(item["relative_path"].startswith("forms/"))

    def test_admin_accepts_form_excel_upload_with_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = Path(temporary_dir)
            sop_path = data_dir / "SOP - Manual.pdf"
            sop_path.write_bytes(b"%PDF-1.4\n")

            with (
                patch.dict(os.environ, {"DATA_DIR": str(data_dir)}),
                patch("backend.api.routes_admin._require_admin", side_effect=_auth_ok),
            ):
                response = self.client.post(
                    "/api/admin/documents",
                    json={
                        "filename": "Spreadsheet Form.xlsx",
                        "content_base64": _b64(b"xlsx"),
                        "document_kind": "form",
                        "linked_sop_path": sop_path.name,
                    },
                )

        self.assertEqual(response.status_code, 200)
        item = response.json()["item"]
        self.assertEqual(item["document_kind"], "form")
        self.assertEqual(item["doc_type"], "xlsx")
        self.assertEqual(item["formats"], ["xlsx"])

    def test_admin_accepts_form_upload_linked_to_non_sop_document(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = Path(temporary_dir)
            document_path = data_dir / "Tata Tertib Kebersihan.pdf"
            document_path.write_bytes(b"%PDF-1.4\n")

            with (
                patch.dict(os.environ, {"DATA_DIR": str(data_dir)}),
                patch("backend.api.routes_admin._require_admin", side_effect=_auth_ok),
            ):
                response = self.client.post(
                    "/api/admin/documents",
                    json={
                        "filename": "Checklist.xlsx",
                        "content_base64": _b64(b"xlsx"),
                        "document_kind": "form",
                        "linked_sop_path": document_path.name,
                    },
                )
                library_response = self.client.get("/api/library")

        self.assertEqual(response.status_code, 200)
        item = response.json()["item"]
        self.assertEqual(item["document_kind"], "form")
        self.assertEqual(item["linked_sop_path"], document_path.name)
        form_items = [
            item
            for item in library_response.json()
            if item["document_kind"] == "form"
        ]
        self.assertEqual(form_items[0]["linked_sop_path"], document_path.name)

    def test_admin_rejects_non_form_excel_upload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = Path(temporary_dir)

            with (
                patch.dict(os.environ, {"DATA_DIR": str(data_dir)}),
                patch("backend.api.routes_admin._require_admin", side_effect=_auth_ok),
            ):
                response = self.client.post(
                    "/api/admin/documents",
                    json={
                        "filename": "Budget.xlsx",
                        "content_base64": _b64(b"xlsx"),
                    },
                )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Excel hanya didukung", response.json()["detail"])

    def test_library_hides_form_docx_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = Path(temporary_dir)
            (data_dir / "Form - Library Test.pdf").write_bytes(b"%PDF-1.4\n")
            (data_dir / "Form - Library Test.docx").write_bytes(b"docx")
            forms_dir = data_dir / "forms" / "visible"
            forms_dir.mkdir(parents=True)
            (forms_dir / "Manual Word.docx").write_bytes(b"docx")
            (data_dir / "SOP - Visible.docx").write_bytes(b"docx")

            with (
                patch.dict(os.environ, {"DATA_DIR": str(data_dir)}),
                patch("backend.api.routes_admin._require_admin", side_effect=_auth_ok),
            ):
                response = self.client.get("/api/library")

        self.assertEqual(response.status_code, 200)
        names = [item["name"] for item in response.json()]
        self.assertIn("Form - Library Test.pdf", names)
        self.assertIn("Manual Word.docx", names)
        self.assertIn("SOP - Visible.docx", names)
        self.assertNotIn("Form - Library Test.docx", names)

    def test_guest_can_list_library_documents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = Path(temporary_dir)
            (data_dir / "SOP - Guest Visible.pdf").write_bytes(b"%PDF-1.4\n")

            with patch.dict(os.environ, {"DATA_DIR": str(data_dir)}):
                response = self.client.get("/api/library")

        self.assertEqual(response.status_code, 200)
        names = [item["name"] for item in response.json()]
        self.assertIn("SOP - Guest Visible.pdf", names)

    def test_related_forms_match_sop_aliases_and_custom_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = Path(temporary_dir)
            (data_dir / "SOP - Kontrol Akses (Template).pdf").write_bytes(b"%PDF-1.4\n")
            (data_dir / "Form - System Access Control List (Template).pdf").write_bytes(
                b"%PDF-1.4\n"
            )
            forms_dir = data_dir / "forms" / "kontrol-akses"
            forms_dir.mkdir(parents=True)
            (forms_dir / "Access Matrix.xlsx").write_bytes(b"xlsx")

            with patch.dict(os.environ, {"DATA_DIR": str(data_dir)}):
                forms = _iter_form_downloads()
                related = _related_form_downloads_for_citations(
                    question="What access request form should I use?",
                    answer="Use the access control process. [1]",
                    citations=[{"source": "SOP - Kontrol Akses (Template).pdf"}],
                    forms=forms,
                )

        names = {form.name for form in related}
        self.assertIn("Form - System Access Control List (Template).pdf", names)
        self.assertIn("Access Matrix.xlsx", names)

    def test_admin_organogram_upload_uses_persistent_faq_assets_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            data_dir = root / "data"
            faq_assets_dir = root / "faq_assets"
            data_dir.mkdir()
            image_bytes = b"\x89PNG\r\n\x1a\norganogram"

            with (
                patch.dict(
                    os.environ,
                    {
                        "DATA_DIR": str(data_dir),
                        "FAQ_ASSETS_DIR": str(faq_assets_dir),
                    },
                ),
                patch("backend.api.routes_admin._require_admin", side_effect=_auth_ok),
            ):
                response = self.client.post(
                    "/api/admin/faq-image",
                    headers={"Authorization": "Bearer test"},
                    json={
                        "filename": "new-organogram.png",
                        "content_base64": _b64(image_bytes),
                    },
                )
                faq_response = self.client.get("/api/faq")
                image_response = self.client.get("/api/faq-image/organogram.png")

            uploaded_path = faq_assets_dir / "organogram.png"
            uploaded_bytes = uploaded_path.read_bytes()

            self.assertEqual(response.status_code, 200)
            self.assertEqual(uploaded_bytes, image_bytes)
            self.assertEqual(faq_response.status_code, 200)
            self.assertIn("/api/faq-image/organogram.png", faq_response.json()[0]["image_url"])
            self.assertEqual(image_response.status_code, 200)
            self.assertEqual(image_response.content, image_bytes)


class RemovedFormEditorStaticTests(unittest.TestCase):
    def test_frontend_has_no_removed_form_editor_references(self) -> None:
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
        self.assertIn("templateDownloadFormats(url, filename, [\"pdf\", \"docx\"])", combined)
        self.assertIn("withDownloadFormat(url, \"docx\")", combined)
        self.assertNotIn('appendLibrarySection("Forms"', combined)
        self.assertIn('document_kind: options.documentKind || null', combined)
        self.assertIn('linked_sop_path: options.linkedSopPath || null', combined)
        self.assertIn("createInsertFormRow", combined)
        self.assertIn("related-form-insert", combined)
        self.assertIn("saveFormDocumentsForSop", combined)
        self.assertIn('id="formFileInput"', combined)
        self.assertIn("multiple", combined)
        self.assertIn("createDocumentLibraryGroup", combined)
        self.assertIn("activeDocumentFormPath", combined)
        self.assertIn("toggleDocumentForms", combined)
        self.assertIn("is-forms-open", combined)
        self.assertIn("document-expand", combined)
        self.assertIn("data-doc-type", combined)
        self.assertIn("const linkedSopPath = state.pendingFormSopPath", combined)
        self.assertIn("formsForDocument", combined)
        self.assertIn("const allFormItems = state.documents.filter", combined)
        self.assertIn('appendLibrarySection("Documents", documentItems, allFormItems)', combined)
        self.assertNotIn("Unlinked forms", combined)
        self.assertNotIn("No related forms yet", combined)
        self.assertNotIn('item.document_kind === "sop"', combined)
        self.assertNotIn("Replace form", combined)
        self.assertNotIn("related-form-add", combined)


if __name__ == "__main__":
    unittest.main()
