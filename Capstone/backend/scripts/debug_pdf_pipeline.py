from __future__ import annotations

import argparse
import re
from pathlib import Path

from backend.preprocessing.chunker import chunk_documents
from backend.preprocessing.ingest import _format_chunk_debug, get_data_dir
from backend.preprocessing.loader import _load_single_document

DEFAULT_SOURCE_NAME = "SOP - Perjalanan Dinas.pdf"


def _resolve_sources(query: str, include_all: bool) -> list[Path]:
    sources = sorted(path for path in get_data_dir().rglob("*") if path.suffix.lower() in {".pdf", ".docx", ".txt"})
    if include_all:
        return sources
    lowered = query.lower()
    matches = [path for path in sources if lowered in path.name.lower()]
    if not matches:
        raise FileNotFoundError(f"Source document not found for query: {query}")
    return [matches[0]]


def _slug(path: Path) -> str:
    return re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-") or "document"


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump final chunks prepared for embedding.")
    parser.add_argument("source", nargs="?", default=DEFAULT_SOURCE_NAME)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    debug_dir = get_data_dir().parent / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    for source_path in _resolve_sources(args.source, args.all):
        chunks = chunk_documents(_load_single_document(source_path))
        output_path = debug_dir / f"{_slug(source_path)}.md"
        output_path.write_text(_format_chunk_debug(chunks), encoding="utf-8")
        print(f"Source: {source_path}")
        print(f"Chunks created: {len(chunks)}")
        print(f"Final chunk file: {output_path}")


if __name__ == "__main__":
    main()
