from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

from langchain_core.documents import Document

from backend.api.flowchart_service import prune_stale_flowchart_cache
from backend.settings import get_env, load_capstone_env
from backend.preprocessing.chunker import chunk_documents
from backend.preprocessing.flowchart_extractor import (
    get_flowchart_timing,
    reset_flowchart_timing,
)
from backend.preprocessing.loader import load_documents
from backend.preprocessing.vectorstore import get_chroma_dir, rebuild_vectorstore

load_capstone_env()


ROOT_DIR = Path(__file__).resolve().parents[2]
CITATION_SCHEMA_MARKER = ".citation-metadata-v1"


def get_data_dir() -> Path:
    # Tentukan folder dokumen sumber untuk proses ingest.
    raw_dir = get_env("DATA_DIR", "backend/data")
    path = Path(raw_dir)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def get_chunk_debug_path() -> Path:
    # Dump final chunks yang sama dengan input embedding.
    # Lokal: backend/data -> backend/debug/chunks.md.
    # Docker: /app/storage/data -> /app/storage/debug/chunks.md.
    return get_data_dir().parent / "debug" / "chunks.md"


def _format_chunk_debug(chunks: list[Document]) -> str:
    lines = [
        "# Ingest Chunk Debug",
        "",
        f"Chunks created: {len(chunks)}",
        "",
    ]
    for index, chunk in enumerate(chunks, start=1):
        metadata = dict(chunk.metadata)
        lines.extend(
            [
                f"## Chunk {index}",
                "",
                "```json",
                json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True),
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


def main() -> None:
    # Muat dokumen, pecah jadi chunk, lalu bangun ulang vector DB.
    total_started_at = perf_counter()

    print("[1/3] Loading documents and extracting flowcharts...")
    stage_started_at = perf_counter()
    reset_flowchart_timing()
    data_dir = get_data_dir()
    documents = load_documents(data_dir)
    removed_flowcharts = prune_stale_flowchart_cache(
        {path.name for path in data_dir.rglob("*.pdf") if path.is_file()}
    )
    load_seconds = perf_counter() - stage_started_at
    flowchart_seconds, flowchart_count = get_flowchart_timing()
    flowchart_enabled = get_env("FLOWCHART_EXTRACTION_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    print(f"[1/3] Loaded {len(documents)} source documents in {load_seconds:.2f}s.")
    print(
        "[flowchart] "
        f"enabled={str(flowchart_enabled).lower()}, "
        f"extracted={flowchart_count}, "
        f"pruned={removed_flowcharts}, "
        f"time={flowchart_seconds:.2f}s."
    )

    print("[2/3] Chunking documents...")
    stage_started_at = perf_counter()
    chunks = chunk_documents(documents)
    chunk_seconds = perf_counter() - stage_started_at
    print(f"[2/3] Created {len(chunks)} chunks in {chunk_seconds:.2f}s.")
    chunk_debug_path = write_chunk_debug(chunks)
    if chunk_debug_path is not None:
        print(f"[debug] Chunk debug written to {chunk_debug_path}.")

    print("[3/3] Rebuilding vector database...")
    stage_started_at = perf_counter()
    rebuild_vectorstore(chunks)
    vector_seconds = perf_counter() - stage_started_at
    (get_chroma_dir() / CITATION_SCHEMA_MARKER).write_text("1\n", encoding="ascii")

    # Index baru tidak punya cache; buang entri cache lama agar tidak menumpuk.
    from backend.semantic_cache import reset_semantic_cache

    reset_semantic_cache()
    total_seconds = perf_counter() - total_started_at

    print(f"[3/3] Vector database rebuilt in {vector_seconds:.2f}s.")
    print(
        "Preprocessing completed "
        f"in {total_seconds:.2f}s "
        f"(load={load_seconds:.2f}s, flowchart={flowchart_seconds:.2f}s, "
        f"chunk={chunk_seconds:.2f}s, "
        f"vector={vector_seconds:.2f}s)."
    )


if __name__ == "__main__":
    main()
