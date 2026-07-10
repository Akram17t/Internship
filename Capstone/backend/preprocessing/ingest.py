from __future__ import annotations

from pathlib import Path
from time import perf_counter

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


def main() -> None:
    # Muat dokumen, pecah jadi chunk, lalu bangun ulang vector DB.
    total_started_at = perf_counter()

    print("[1/3] Loading documents and extracting flowcharts...")
    stage_started_at = perf_counter()
    reset_flowchart_timing()
    documents = load_documents(get_data_dir())
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
        f"time={flowchart_seconds:.2f}s."
    )

    print("[2/3] Chunking documents...")
    stage_started_at = perf_counter()
    chunks = chunk_documents(documents)
    chunk_seconds = perf_counter() - stage_started_at
    print(f"[2/3] Created {len(chunks)} chunks in {chunk_seconds:.2f}s.")

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
