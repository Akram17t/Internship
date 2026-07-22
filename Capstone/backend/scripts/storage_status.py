from __future__ import annotations

import sys
from pathlib import Path

from backend.settings import ROOT_DIR, get_env, load_capstone_env
from backend.cache_db import state_counts
from backend.preprocessing.ingest import CITATION_SCHEMA_MARKER
from backend.preprocessing.vectorstore import ACTIVE_INDEX_FILE


SOURCE_EXTENSIONS = {".pdf", ".docx", ".txt"}


def _resolve_env_path(name: str, default: str) -> Path:
    # Tentukan path konfigurasi relatif ke root project bila perlu.
    load_capstone_env()
    path = Path(get_env(name, default))
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path.resolve()


def has_source_documents() -> bool:
    # Cek apakah ada dokumen sumber yang bisa di-embed.
    data_dir = _resolve_env_path("DATA_DIR", "backend/data")
    if not data_dir.exists():
        return False
    return any(
        path.is_file() and path.suffix.lower() in SOURCE_EXTENSIONS
        for path in data_dir.rglob("*")
    )


def _is_inside(child: Path, parent: Path) -> bool:
    # Kembalikan True jika path tetap berada di dalam parent yang aman.
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def has_valid_vector_db() -> bool:
    # Cek apakah vector DB aktif ada dan punya marker citation schema.
    chroma_base = _resolve_env_path("CHROMA_DIR", "backend/chroma_db")
    if not chroma_base.exists():
        return False

    active_file = chroma_base / ACTIVE_INDEX_FILE
    if active_file.exists():
        active_name = active_file.read_text(encoding="utf-8").strip()
        active_dir = (chroma_base / active_name).resolve()
        return (
            _is_inside(active_dir, chroma_base)
            and active_dir.exists()
            and (active_dir / CITATION_SCHEMA_MARKER).exists()
        )

    return (chroma_base / CITATION_SCHEMA_MARKER).exists()


def main() -> int:
    # Sediakan cek CLI sederhana untuk source docs dan vector DB.
    command = sys.argv[1] if len(sys.argv) > 1 else "vector-db"
    if command == "vector-db":
        return 0 if has_valid_vector_db() else 1
    if command == "source-docs":
        return 0 if has_source_documents() else 1
    if command == "app-state":
        counts = state_counts()
        print(
            "conversation_messages={conversation_messages} "
            "semantic_cache_entries={semantic_cache_entries} "
            "admin_accounts={admin_accounts} "
            "faq_items={faq_items}".format(**counts)
        )
        return 0

    print("Usage: python -m backend.scripts.storage_status [vector-db|source-docs|app-state]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
