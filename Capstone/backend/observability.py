from __future__ import annotations

import contextlib
import os
import re
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

from backend.settings import get_env, load_capstone_env


load_capstone_env()

_SENSITIVE_PATTERNS = [
    re.compile(r"data:image/[A-Za-z0-9.+-]+;base64,[A-Za-z0-9+/=]+"),
    re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9._-]{8,}\b"),
    re.compile(r"\bpk-[A-Za-z0-9][A-Za-z0-9._-]{8,}\b"),
    re.compile(r"(?i)\b(bearer|token|api[_-]?key|secret)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)"),
]
_DEFAULT_TEXT_LIMIT = 1200
_LANGFUSE_CLIENT: Any | None = None


class NoopObservation:
    def update(self, **_: Any) -> None:
        return None

    def __enter__(self) -> NoopObservation:
        return self

    def __exit__(self, *_: Any) -> None:
        return None


def _enabled_flag() -> bool:
    return get_env("LANGFUSE_TRACING_ENABLED", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def is_enabled() -> bool:
    if not _enabled_flag():
        return False
    return bool(
        get_env("LANGFUSE_PUBLIC_KEY", "")
        and get_env("LANGFUSE_SECRET_KEY", "")
        and _langfuse_base_url()
    )


def _langfuse_base_url() -> str:
    return get_env("LANGFUSE_BASE_URL", get_env("LANGFUSE_HOST", "")).rstrip("/")


def _configure_langfuse_env() -> None:
    base_url = _langfuse_base_url()
    if base_url:
        os.environ.setdefault("LANGFUSE_HOST", base_url)
        os.environ.setdefault("LANGFUSE_BASE_URL", base_url)
    os.environ.setdefault("LANGFUSE_TRACING_ENVIRONMENT", environment_name())


def _client() -> Any | None:
    global _LANGFUSE_CLIENT
    if not is_enabled():
        return None
    if _LANGFUSE_CLIENT is not None:
        return _LANGFUSE_CLIENT
    _configure_langfuse_env()
    try:
        from langfuse import Langfuse
    except Exception:
        return None
    try:
        _LANGFUSE_CLIENT = Langfuse(
            environment=environment_name(),
            mask_otel_spans=_mask_otel_spans,
        )
        return _LANGFUSE_CLIENT
    except Exception:
        return None


def _mask_otel_spans(*, params: Any) -> Any | None:
    try:
        from langfuse.types import MaskOtelSpansResult, OtelSpanPatch
    except Exception:
        return None

    patches: dict[object, object] = {}
    for identifier, otel_span in getattr(params, "spans", {}).items():
        replacements: dict[str, object] = {}
        for key, value in getattr(otel_span, "attributes", {}).items():
            if isinstance(value, str):
                masked_value = redact(value)
                if masked_value != value:
                    replacements[key] = masked_value
        if replacements:
            patches[identifier] = OtelSpanPatch(set_attributes=replacements)
    if not patches:
        return None
    return MaskOtelSpansResult(span_patches=patches)


def environment_name() -> str:
    return get_env(
        "LANGFUSE_TRACING_ENVIRONMENT",
        get_env("LANGFUSE_ENVIRONMENT", get_env("ENVIRONMENT", "development")),
    )


def trace_io_mode() -> str:
    mode = get_env("LANGFUSE_TRACE_IO_MODE", "masked").lower()
    return mode if mode in {"masked", "full", "none"} else "masked"


def redact(value: object, *, limit: int = _DEFAULT_TEXT_LIMIT) -> object:
    mode = trace_io_mode()
    if mode == "none":
        return None
    if isinstance(value, dict):
        return {str(key): redact(item, limit=limit) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, limit=limit) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value

    text = str(value)
    if mode == "masked":
        for pattern in _SENSITIVE_PATTERNS:
            text = pattern.sub("[redacted]", text)
    if len(text) > limit:
        text = f"{text[:limit].rstrip()}... [truncated]"
    return text


def base_url_host(base_url: str) -> str:
    parsed = urlparse(str(base_url))
    return parsed.netloc or parsed.path


def openai_client_class() -> Any:
    if is_enabled():
        _configure_langfuse_env()
        _client()
        try:
            from langfuse.openai import OpenAI

            return OpenAI
        except Exception:
            pass
    from openai import OpenAI

    return OpenAI


def openai_observation_kwargs(
    name: str,
    *,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    if not is_enabled():
        return {}
    return {
        "name": name,
        "metadata": redact(metadata or {}, limit=600),
    }


@contextlib.contextmanager
def trace_context(
    *,
    name: str,
    session_id: str,
    input: object = None,
    metadata: dict[str, object] | None = None,
    tags: list[str] | None = None,
) -> Iterator[Any]:
    client = _client()
    if client is None:
        yield NoopObservation()
        return

    try:
        from langfuse import propagate_attributes
    except Exception:
        yield NoopObservation()
        return

    with client.start_as_current_observation(as_type="span", name=name) as observation:
        observation.update(
            input=redact(input),
            metadata=redact(metadata or {}, limit=600),
        )
        with propagate_attributes(
            session_id=session_id,
            tags=tags or [],
            environment=environment_name(),
        ):
            yield observation


@contextlib.contextmanager
def span(
    name: str,
    *,
    input: object = None,
    metadata: dict[str, object] | None = None,
    as_type: str = "span",
) -> Iterator[Any]:
    client = _client()
    if client is None:
        yield NoopObservation()
        return

    with client.start_as_current_observation(as_type=as_type, name=name) as observation:
        observation.update(
            input=redact(input),
            metadata=redact(metadata or {}, limit=600),
        )
        yield observation


def update_observation(
    observation: Any,
    *,
    output: object = None,
    metadata: dict[str, object] | None = None,
    error: object = None,
) -> None:
    payload: dict[str, object] = {}
    if output is not None:
        payload["output"] = redact(output)
    if metadata is not None:
        payload["metadata"] = redact(metadata, limit=600)
    if error is not None:
        payload["level"] = "ERROR"
        payload["status_message"] = str(redact(error, limit=400))
    try:
        observation.update(**payload)
    except Exception:
        return


def current_trace_id() -> str:
    client = _client()
    if client is None:
        return ""
    try:
        return str(client.get_current_trace_id() or "")
    except Exception:
        return ""


def score_user_thumbs_down(
    *,
    trace_id: str,
    feedback_id: int,
    reason: str,
    conversation_id: str,
) -> bool:
    clean_trace_id = str(trace_id or "").strip()
    if not clean_trace_id:
        return False
    client = _client()
    if client is None:
        return False
    try:
        client.create_score(
            trace_id=clean_trace_id,
            name="user-thumbs-down",
            value=0,
            score_id=f"user-thumbs-down:{feedback_id}",
            data_type="BOOLEAN",
            comment=str(redact(reason, limit=500) or ""),
            metadata=redact(
                {
                    "feedback_id": feedback_id,
                    "conversation_id": conversation_id,
                    "source": "capstone-feedback-modal",
                },
                limit=500,
            ),
            environment=environment_name(),
        )
        return True
    except Exception:
        return False


def shutdown() -> None:
    client = _client()
    if client is None:
        return
    try:
        client.shutdown()
    except Exception:
        return
