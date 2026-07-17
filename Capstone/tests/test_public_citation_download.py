from __future__ import annotations

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


class PublicCitationDownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_guest_can_download_embeddable_citation_document(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = Path(temporary_dir)
            source = data_dir / "SOP Guest Access.pdf"
            source.write_bytes(b"%PDF-1.4\n% citation fixture\n")

            with patch.dict(os.environ, {"DATA_DIR": str(data_dir)}):
                response = self.client.get(f"/api/citations/{quote(source.name, safe='')}")

        self.assertEqual(response.status_code, 200)
        self.assertIn("application/pdf", response.headers["content-type"])
        self.assertEqual(response.content, b"%PDF-1.4\n% citation fixture\n")

    def test_guest_can_download_library_document_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = Path(temporary_dir)
            source = data_dir / "SOP Guest Download.pdf"
            source.write_bytes(b"%PDF-1.4\n% library fixture\n")

            with patch.dict(os.environ, {"DATA_DIR": str(data_dir)}):
                response = self.client.get(f"/api/documents/{quote(source.name, safe='')}")

        self.assertEqual(response.status_code, 200)
        self.assertIn("application/pdf", response.headers["content-type"])
        self.assertEqual(response.content, b"%PDF-1.4\n% library fixture\n")

    def test_library_pdf_cannot_be_downloaded_as_word(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = Path(temporary_dir)
            source = data_dir / "SOP Guest Download.pdf"
            source.write_bytes(b"%PDF-1.4\n% library fixture\n")

            with patch.dict(os.environ, {"DATA_DIR": str(data_dir)}):
                response = self.client.get(
                    f"/api/documents/{quote(source.name, safe='')}?format=docx",
                )

        self.assertEqual(response.status_code, 400)

    def test_form_template_is_not_public_through_citation_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = Path(temporary_dir)
            source = data_dir / "Form - Guest Access.pdf"
            source.write_bytes(b"%PDF-1.4\n% form fixture\n")

            with patch.dict(os.environ, {"DATA_DIR": str(data_dir)}):
                response = self.client.get(f"/api/citations/{quote(source.name, safe='')}")

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
