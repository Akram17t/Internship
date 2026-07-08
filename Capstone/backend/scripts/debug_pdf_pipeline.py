from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.preprocessing.chunker import (
    _clean_page_text,
    _is_table_row,
    _merge_section_segments,
    chunk_documents,
    split_documents_by_section,
)
from backend.preprocessing.loader import _load_single_document
from backend.settings import get_env, load_capstone_env


DEFAULT_SOURCE_NAME = "SOP - Perjalanan Dinas.pdf"
DEBUG_DIR_NAME = "debug"


def _get_data_dir() -> Path:
    load_capstone_env()
    raw_dir = get_env("DATA_DIR", "backend/data")
    path = Path(raw_dir)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return cleaned or "document"


def _resolve_source_path(requested_name: str) -> Path:
    data_dir = _get_data_dir()
    exact_path = data_dir / requested_name
    if exact_path.exists():
        return exact_path

    candidates = sorted(path for path in data_dir.rglob("*.pdf") if path.is_file())
    normalized_query = requested_name.strip().lower()
    for path in candidates:
        if path.name.lower() == normalized_query:
            return path
    for path in candidates:
        if normalized_query in path.name.lower():
            return path

    raise FileNotFoundError(f"PDF source not found for query: {requested_name}")


def _iter_source_paths(requested_name: str, include_all: bool) -> list[Path]:
    data_dir = _get_data_dir()
    if include_all:
        return sorted(path for path in data_dir.rglob("SOP*.pdf") if path.is_file())
    return [_resolve_source_path(requested_name)]


def _write_raw_extract(path: Path, documents: list[object], output_path: Path) -> None:
    lines = [
        f"Source: {path}",
        f"Pages loaded: {len(documents)}",
        "",
    ]
    for index, document in enumerate(documents, start=1):
        metadata = getattr(document, "metadata", {})
        page_number = metadata.get("page")
        lines.extend(
            [
                f"# Page {index}",
                f"Loader page metadata: {page_number}",
                "```text",
                getattr(document, "page_content", ""),
                "```",
                "",
            ]
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _write_cleaned_pages(path: Path, documents: list[object], output_path: Path) -> None:
    lines = [
        f"Source: {path}",
        f"Pages loaded: {len(documents)}",
        "",
    ]
    for index, document in enumerate(documents, start=1):
        metadata = getattr(document, "metadata", {})
        lines.extend(
            [
                f"# Cleaned Page {index}",
                f"Loader page metadata: {metadata.get('page')}",
                "```text",
                _clean_page_text(document),
                "```",
                "",
            ]
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _write_section_debug(path: Path, sections: list[object], output_path: Path, title: str) -> None:
    lines = [
        f"Source: {path}",
        f"{title}: {len(sections)}",
        "",
    ]
    for index, section in enumerate(sections, start=1):
        metadata = getattr(section, "metadata", {})
        lines.extend(
            [
                f"# Section {index}",
                f"- page: {metadata.get('page')}",
                f"- page_end: {metadata.get('page_end')}",
                f"- section: {metadata.get('section')}",
                f"- anomaly: {metadata.get('anomaly')}",
                "```text",
                getattr(section, "page_content", ""),
                "```",
                "",
            ]
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _write_chunk_debug(path: Path, chunks: list[object], output_path: Path) -> None:
    lines = [
        f"Source: {path}",
        f"Chunks created: {len(chunks)}",
        "",
    ]
    for index, chunk in enumerate(chunks, start=1):
        metadata = getattr(chunk, "metadata", {})
        lines.extend(
            [
                f"# Chunk {index}",
                f"- chunk_id: {metadata.get('chunk_id')}",
                f"- page: {metadata.get('page')}",
                f"- page_end: {metadata.get('page_end')}",
                f"- section: {metadata.get('section')}",
                f"- anomaly: {metadata.get('anomaly')}",
                f"- source: {metadata.get('source')}",
                "```text",
                getattr(chunk, "page_content", ""),
                "```",
                "",
            ]
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _compact_text(value: str, limit: int = 220) -> str:
    text = " ".join(value.split())
    return text[:limit]


def _write_anomaly_report(
    path: Path,
    sections: list[object],
    merged_sections: list[object],
    chunks: list[object],
    output_path: Path,
) -> None:
    false_section_pattern = re.compile(r"^\d+\.?\s+[A-Z][a-z]|^[A-Z0-9/&(),'\-]+$")
    template_pattern = re.compile(r"(?im)^\s*\[nama perusahaan\](?:\s+.+)?$")
    table_header_pattern = re.compile(
        r"(?i)(peran\s+tanggung\s+jawab|nomor\s+form\s+nama\s+form|"
        r"no\s+proses\s+pic\s+sasaran|destinasi\s+jabatan|jabatan\s+requestor)"
    )
    table_row_pattern = re.compile(r"(?i)\b(?:rp|usd)\s*\d")

    section_counts: dict[str, int] = {}
    for section in sections:
        name = str(getattr(section, "metadata", {}).get("section") or "")
        if name:
            section_counts[name] = section_counts.get(name, 0) + 1

    lines = [
        f"Source: {path}",
        "",
        "# False-section candidates",
    ]
    for index, section in enumerate(sections, start=1):
        metadata = getattr(section, "metadata", {})
        name = str(metadata.get("section") or "")
        if name and false_section_pattern.match(name):
            lines.append(
                f"- segment={index} page={metadata.get('page')} section={name!r} "
                f"text={_compact_text(getattr(section, 'page_content', ''))}"
            )

    lines.extend(["", "# Repeated section segments"])
    for name, count in section_counts.items():
        if count > 1:
            lines.append(f"- {name!r}: {count} segments before merge")

    lines.extend(["", "# No-section content"])
    for index, section in enumerate(sections, start=1):
        metadata = getattr(section, "metadata", {})
        if not metadata.get("section") and getattr(section, "page_content", "").strip():
            lines.append(
                f"- segment={index} page={metadata.get('page')} "
                f"text={_compact_text(getattr(section, 'page_content', ''))}"
            )

    lines.extend(["", "# Template/title noise"])
    for index, section in enumerate(merged_sections, start=1):
        metadata = getattr(section, "metadata", {})
        text = getattr(section, "page_content", "")
        if template_pattern.search(text):
            lines.append(
                f"- merged_segment={index} page={metadata.get('page')} "
                f"section={metadata.get('section')!r} text={_compact_text(text)}"
            )

    lines.extend(["", "# Header-only table chunks"])
    for chunk in chunks:
        metadata = getattr(chunk, "metadata", {})
        text = getattr(chunk, "page_content", "")
        has_table_row = any(_is_table_row(line) for line in text.splitlines())
        if table_header_pattern.search(text) and not table_row_pattern.search(text) and not has_table_row:
            lines.append(
                f"- chunk={metadata.get('chunk_id')} page={metadata.get('page')} "
                f"section={metadata.get('section')!r} text={_compact_text(text)}"
            )

    lines.extend(["", "# Row-only table chunks"])
    for chunk in chunks:
        metadata = getattr(chunk, "metadata", {})
        text = getattr(chunk, "page_content", "")
        if table_row_pattern.search(text) and not table_header_pattern.search(text):
            lines.append(
                f"- chunk={metadata.get('chunk_id')} page={metadata.get('page')} "
                f"section={metadata.get('section')!r} text={_compact_text(text)}"
            )

    lines.extend(["", "# Lone bullet/out-of-order candidates"])
    for index, section in enumerate(merged_sections, start=1):
        metadata = getattr(section, "metadata", {})
        text = getattr(section, "page_content", "")
        if metadata.get("anomaly") or re.search(r"(?m)^\s*[•-]\s*$", text):
            lines.append(
                f"- merged_segment={index} page={metadata.get('page')} "
                f"section={metadata.get('section')!r} anomaly={metadata.get('anomaly')!r} "
                f"text={_compact_text(text)}"
            )

    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dump raw PDF extraction output and final chunks for debugging."
    )
    parser.add_argument(
        "source",
        nargs="?",
        default=DEFAULT_SOURCE_NAME,
        help="Exact filename or substring of the PDF to inspect.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate debug files for every SOP PDF in DATA_DIR.",
    )
    args = parser.parse_args()

    debug_dir = PROJECT_ROOT / "backend" / DEBUG_DIR_NAME
    debug_dir.mkdir(parents=True, exist_ok=True)

    for source_path in _iter_source_paths(args.source, args.all):
        documents = _load_single_document(source_path)
        section_segments = split_documents_by_section(documents)
        merged_sections = _merge_section_segments(section_segments)
        chunks = chunk_documents(documents)

        slug = _slugify(source_path.stem)
        raw_output_path = debug_dir / f"{slug}.raw-extract.md"
        cleaned_output_path = debug_dir / f"{slug}.cleaned.md"
        sections_output_path = debug_dir / f"{slug}.sections.md"
        merged_output_path = debug_dir / f"{slug}.merged-sections.md"
        chunk_output_path = debug_dir / f"{slug}.chunks.md"
        anomaly_output_path = debug_dir / f"{slug}.anomalies.md"

        _write_raw_extract(source_path, documents, raw_output_path)
        _write_cleaned_pages(source_path, documents, cleaned_output_path)
        _write_section_debug(source_path, section_segments, sections_output_path, "Section segments")
        _write_section_debug(source_path, merged_sections, merged_output_path, "Merged sections")
        _write_chunk_debug(source_path, chunks, chunk_output_path)
        _write_anomaly_report(
            source_path,
            section_segments,
            merged_sections,
            chunks,
            anomaly_output_path,
        )

        print(f"Source PDF: {source_path}")
        print(f"Pages loaded: {len(documents)}")
        print(f"Section segments: {len(section_segments)}")
        print(f"Merged sections: {len(merged_sections)}")
        print(f"Chunks created: {len(chunks)}")
        print(f"Raw extract file: {raw_output_path}")
        print(f"Cleaned text file: {cleaned_output_path}")
        print(f"Section debug file: {sections_output_path}")
        print(f"Merged section file: {merged_output_path}")
        print(f"Chunk debug file: {chunk_output_path}")
        print(f"Anomaly report file: {anomaly_output_path}")


if __name__ == "__main__":
    main()
