from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

from langchain_core.documents import Document

from backend.preprocessing.chunker import chunk_documents
from backend.preprocessing.loader import load_documents
from backend.preprocessing.vectorstore import clear_vectorstore, get_chroma_dir, rebuild_vectorstore
from backend.settings import get_env, load_capstone_env

load_capstone_env()

ROOT_DIR = Path(__file__).resolve().parents[2]
CITATION_SCHEMA_MARKER = ".citation-metadata-v1"


def get_data_dir() -> Path:
    path = Path(get_env("DATA_DIR", "backend/data"))
    return path if path.is_absolute() else ROOT_DIR / path


def get_chunk_debug_path() -> Path:
    return get_data_dir().parent / "debug" / "chunks.md"


def _format_chunk_debug(chunks: list[Document]) -> str:
    lines = ["# Ingest Chunk Debug", "", f"Chunks created: {len(chunks)}", ""]
    for index, chunk in enumerate(chunks, start=1):
        lines.extend(
            [
                f"## Chunk {index}",
                "",
                "```json",
                json.dumps(dict(chunk.metadata), ensure_ascii=False, indent=2, sort_keys=True),
                "```",
                "",
                "```text",
                chunk.page_content,
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_chunk_debug(chunks: list[Document]) -> Path:
    output_path = get_chunk_debug_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_format_chunk_debug(chunks), encoding="utf-8")
    return output_path


def _is_empty_source_error(error: ValueError) -> bool:
    return str(error).startswith("No supported documents found in:")


def main() -> str:
    total_started_at = perf_counter()
    print("[1/3] Loading documents...")
    stage_started_at = perf_counter()
    data_dir = get_data_dir()
    try:
        documents = load_documents(data_dir)
    except FileNotFoundError:
        data_dir.mkdir(parents=True, exist_ok=True)
        documents = []
    except ValueError as error:
        if not _is_empty_source_error(error):
            raise
        documents = []
    load_seconds = perf_counter() - stage_started_at
    print(f"[1/3] Loaded {len(documents)} page documents in {load_seconds:.2f}s.")

    print("[2/3] Chunking documents...")
    stage_started_at = perf_counter()
    chunks = chunk_documents(documents)
    chunk_seconds = perf_counter() - stage_started_at
    print(f"[2/3] Created {len(chunks)} chunks in {chunk_seconds:.2f}s.")
    print(f"[debug] Chunk debug written to {write_chunk_debug(chunks)}.")

    stage_started_at = perf_counter()
    if not chunks:
        print("[3/3] No source chunks found. Clearing vector database...")
        removed_vectors = clear_vectorstore()
        result = "cleared"
        action = f"cleared ({removed_vectors} files/directories removed)"
    else:
        print("[3/3] Rebuilding vector database...")
        rebuild_vectorstore(chunks)
        (get_chroma_dir() / CITATION_SCHEMA_MARKER).write_text("1\n", encoding="ascii")
        result = "rebuilt"
        action = "rebuilt"

    from backend.semantic_cache import reset_semantic_cache

    reset_semantic_cache()
    vector_seconds = perf_counter() - stage_started_at
    total_seconds = perf_counter() - total_started_at
    print(f"[3/3] Vector database {action} in {vector_seconds:.2f}s.")
    print(
        f"Preprocessing completed in {total_seconds:.2f}s "
        f"(load={load_seconds:.2f}s, chunk={chunk_seconds:.2f}s, vector={vector_seconds:.2f}s)."
    )
    return result


if __name__ == "__main__":
    main()
