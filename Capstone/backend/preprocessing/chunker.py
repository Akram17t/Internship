from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

from backend.observability import openai_client_class, openai_observation_kwargs
from backend.openai_compat import (
    extract_chat_message_content,
    openai_client_kwargs,
    openai_request_kwargs,
    resolve_openai_compatible_api_key,
)
from backend.settings import get_env, get_int_env

LOGGER = logging.getLogger(__name__)
ROOT_DIR = Path(__file__).resolve().parents[2]
FALLBACK_CHUNK_SIZE = 1200
CHUNK_PROMPT_SCHEMA_VERSION = "final-chunks-v1"
_PAGE_MARKER = "--- PAGE {page} ---"
_CACHE_FILENAME = re.compile(r"^[0-9a-f]{64}\.json$")

_SYSTEM_PROMPT = """You split source documents into final retrieval chunks.
Return strict JSON only: {"chunks": [{"content": "...", "metadata": {...}}]}.
Each chunk must contain useful source text, not an outline or boundary list.
Metadata must include page, page_end, section, document_kind, and content_type.
Use the exact zero-based page numbers shown in PAGE markers. Preserve factual text,
table context, and section meaning. Do not add facts or markdown fences."""


def _group_by_source(documents: list[Document]) -> dict[str, list[Document]]:
    grouped: dict[str, list[Document]] = {}
    for document in documents:
        source = str(document.metadata.get("source") or "unknown source")
        grouped.setdefault(source, []).append(document)
    for pages in grouped.values():
        if all(isinstance(page.metadata.get("page"), int) for page in pages):
            pages.sort(key=lambda page: int(page.metadata["page"]))
    return grouped


def _page_number(document: Document, index: int) -> int:
    page = document.metadata.get("page")
    return page if isinstance(page, int) else index


def _source_text(pages: list[Document]) -> str:
    return "\n\n".join(
        f"{_PAGE_MARKER.format(page=_page_number(page, index))}\n{page.page_content.strip()}"
        for index, page in enumerate(pages)
        if page.page_content.strip()
    )


def _model_identity() -> str:
    return get_env("MODEL", "kr/claude-sonnet-4.5")


def _request_ai_chunks(document_text: str, source: str) -> str:
    base_url = get_env("CHAT_BASE_URL", "http://localhost:20128/v1").rstrip("/")
    api_key = resolve_openai_compatible_api_key(
        base_url=base_url,
        primary_env="CHAT_API_KEY",
        fallback_envs=("OPENAI_API_KEY", "ROUTER9_API_KEY", "NINE_ROUTER_API_KEY"),
    )
    client = openai_client_class()(
        **openai_client_kwargs(
            api_key=api_key,
            base_url=base_url,
            timeout=get_int_env("CHAT_TIMEOUT_SECONDS", 240),
        )
    )
    payload: dict[str, Any] = {
        "model": _model_identity(),
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": document_text},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "max_tokens": get_int_env("CHUNK_AI_MAX_COMPLETION_TOKENS", 8192),
        "stream": False,
    }
    payload.update(openai_request_kwargs(api_key=api_key, base_url=base_url))
    payload.update(
        openai_observation_kwargs(
            f"chunk-document: {source}",
            metadata={"operation": "chunk-document", "source": source, "document_chars": len(document_text)},
        )
    )
    return extract_chat_message_content(client.chat.completions.create(**payload))


def _json_values(response_text: str) -> list[Any]:
    text = str(response_text or "").strip()
    candidates = [text]
    candidates.extend(
        match.group("body").strip()
        for match in re.finditer(
            r"```(?:json)?\s*(?P<body>.*?)\s*```", text, re.IGNORECASE | re.DOTALL
        )
    )
    decoder = json.JSONDecoder()
    values: list[Any] = []
    for candidate in candidates:
        try:
            values.append(json.loads(candidate))
        except (json.JSONDecodeError, TypeError):
            pass
        for match in re.finditer(r"[\[{]", candidate):
            try:
                value, _ = decoder.raw_decode(candidate[match.start() :])
            except json.JSONDecodeError:
                continue
            values.append(value)
    return values


def _parse_ai_chunks(response_text: str) -> list[dict[str, Any]]:
    for value in _json_values(response_text):
        entries = value.get("chunks") if isinstance(value, dict) else value
        if not isinstance(entries, list) or not entries:
            continue
        parsed: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                parsed = []
                break
            content = entry.get("content", entry.get("page_content"))
            metadata = entry.get("metadata", {})
            if not isinstance(content, str) or not content.strip() or not isinstance(metadata, dict):
                parsed = []
                break
            top_level_metadata = {
                key: item
                for key, item in entry.items()
                if key not in {"content", "page_content", "metadata"}
            }
            parsed.append(
                {"content": content.strip(), "metadata": {**top_level_metadata, **metadata}}
            )
        if parsed:
            return parsed
    raise ValueError("AI response did not contain a valid non-empty chunk list")


def _source_hash(document_text: str) -> str:
    return hashlib.sha256(document_text.encode("utf-8")).hexdigest()


def _cache_key(source: str, source_hash: str, model: str, prompt_version: str) -> str:
    identity = json.dumps(
        {
            "model": model,
            "prompt_schema_version": prompt_version,
            "source": source,
            "source_hash": source_hash,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _cache_dir() -> Path:
    configured = Path(get_env("CHUNK_CACHE_DIR", "backend/cache/chunks"))
    return configured if configured.is_absolute() else ROOT_DIR / configured


def _cache_path(key: str) -> Path:
    return _cache_dir() / f"{key}.json"


def _read_cache_entry(
    key: str, source: str, source_hash: str, model: str, prompt_version: str
) -> list[dict[str, Any]] | None:
    try:
        payload = json.loads(_cache_path(key).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or any(
            payload.get(field) != expected
            for field, expected in {
                "source": source,
                "source_hash": source_hash,
                "model": model,
                "prompt_schema_version": prompt_version,
            }.items()
        ):
            return None
        return _parse_ai_chunks(json.dumps({"chunks": payload.get("chunks")}))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _write_cache_entry(
    key: str,
    source: str,
    source_hash: str,
    model: str,
    prompt_version: str,
    entries: list[dict[str, Any]],
) -> None:
    cache_dir = _cache_dir()
    temp_path: Path | None = None
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "source": source,
            "source_hash": source_hash,
            "model": model,
            "prompt_schema_version": prompt_version,
            "chunks": entries,
        }
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=cache_dir, delete=False, suffix=".tmp"
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        os.replace(temp_path, _cache_path(key))
        temp_path = None
    except OSError as error:
        LOGGER.warning("Could not write AI chunk cache for %s: %s", source, error)
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _prune_stale_cache(valid_keys: set[str]) -> int:
    cache_dir = _cache_dir()
    if not cache_dir.is_dir():
        return 0
    valid_names = {f"{key}.json" for key in valid_keys}
    removed = 0
    for path in cache_dir.glob("*.json"):
        if not _CACHE_FILENAME.fullmatch(path.name) or path.name in valid_names:
            continue
        try:
            path.unlink()
            removed += 1
        except OSError as error:
            LOGGER.warning("Could not prune stale AI chunk cache %s: %s", path, error)
    return removed


def _base_metadata(source: str, pages: list[Document]) -> dict[str, Any]:
    metadata = dict(pages[0].metadata) if pages else {}
    metadata["source"] = source
    metadata.setdefault("document_kind", "document")
    metadata.setdefault("content_type", "text")
    return metadata


def _documents_from_entries(
    source: str, pages: list[Document], entries: list[dict[str, Any]]
) -> list[Document]:
    base = _base_metadata(source, pages)
    default_page = _page_number(pages[0], 0) if pages else 0
    documents: list[Document] = []
    for entry in entries:
        metadata = {**base, **entry["metadata"]}
        metadata["source"] = source
        page = metadata.get("page")
        page = page if isinstance(page, int) else default_page
        page_end = metadata.get("page_end")
        page_end = page_end if isinstance(page_end, int) else page
        metadata["page"] = min(page, page_end)
        metadata["page_end"] = max(page, page_end)
        metadata["section"] = str(metadata.get("section") or base.get("title") or "Document")
        metadata["document_kind"] = str(metadata.get("document_kind") or "document")
        metadata["content_type"] = str(metadata.get("content_type") or "text")
        documents.append(Document(page_content=entry["content"], metadata=metadata))
    return documents


def _split_approximately(text: str, size: int = FALLBACK_CHUNK_SIZE) -> list[str]:
    remaining = text.strip()
    chunks: list[str] = []
    while remaining:
        if len(remaining) <= size:
            chunks.append(remaining)
            break
        split_at = remaining.rfind(" ", size // 2, size + 1)
        if split_at < 1:
            split_at = size
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    return [chunk for chunk in chunks if chunk]


def _fallback_documents(source: str, pages: list[Document]) -> list[Document]:
    base = _base_metadata(source, pages)
    documents: list[Document] = []
    for index, page_document in enumerate(pages):
        page = _page_number(page_document, index)
        for content in _split_approximately(page_document.page_content):
            metadata = {**base, **page_document.metadata}
            metadata.update(
                {
                    "source": source,
                    "page": page,
                    "page_end": page,
                    "section": str(metadata.get("section") or metadata.get("title") or "Document"),
                    "document_kind": str(metadata.get("document_kind") or "document"),
                    "content_type": str(metadata.get("content_type") or "text"),
                    "fallback": True,
                }
            )
            documents.append(Document(page_content=content, metadata=metadata))
    return documents


def chunk_documents(documents: list[Document]) -> list[Document]:
    model = _model_identity()
    prompt_version = CHUNK_PROMPT_SCHEMA_VERSION
    sources: list[tuple[str, list[Document], str, str, str]] = []
    for source, pages in _group_by_source(documents).items():
        document_text = _source_text(pages)
        if not document_text:
            continue
        source_hash = _source_hash(document_text)
        key = _cache_key(source, source_hash, model, prompt_version)
        sources.append((source, pages, document_text, source_hash, key))

    _prune_stale_cache({key for _, _, _, _, key in sources})
    chunks: list[Document] = []
    for source, pages, document_text, source_hash, key in sources:
        entries = _read_cache_entry(key, source, source_hash, model, prompt_version)
        if entries is not None:
            print(f"[chunk] cache hit  | {source} ({len(entries)} chunks)")
            source_chunks = _documents_from_entries(source, pages, entries)
        else:
            print(f"[chunk] cache miss | {source}; requesting AI chunking...")
            try:
                response_text = _request_ai_chunks(document_text, source)
                if not response_text.strip():
                    raise ValueError("AI returned empty output")
                entries = _parse_ai_chunks(response_text)
                source_chunks = _documents_from_entries(source, pages, entries)
                _write_cache_entry(
                    key, source, source_hash, model, prompt_version, entries
                )
            except Exception as error:
                LOGGER.warning("AI chunking failed for %s; using local fallback: %s", source, error)
                source_chunks = _fallback_documents(source, pages)
        chunks.extend(source_chunks)

    for chunk_id, chunk in enumerate(chunks, start=1):
        chunk.metadata["chunk_id"] = chunk_id
    return chunks
