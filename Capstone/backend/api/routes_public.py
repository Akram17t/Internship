from __future__ import annotations

import logging
import secrets
import time

from fastapi import Header, HTTPException
from fastapi.responses import FileResponse, Response

from backend.api.auth import _require_user, _require_user_from_header_or_query
from backend.api.cache_store import _append_conversation_turn, _clean_conversation_id, _get_conversation_context, _load_faqs
from backend.api.core import FAQ_LOCK, FRONTEND_DIR, app
from backend.api.forms_service import (
    DOCX_MIME,
    get_form_docx_template,
)
from backend.api.models import (
    CitationResponse,
    ConversationMessage,
    ConversationMessagesResponse,
    ConversationRenamePayload,
    ConversationSummary,
    FAQItem,
    FeedbackPayload,
    FeedbackResponse,
    FormDownloadResponse,
    MessageResponse,
    PublicConfigResponse,
    QueryRequest,
    QueryResponse,
)
from backend.api.storage import (
    _answer_has_supported_form_context,
    _citation_download_url,
    _form_catalog_entries,
    _document_kind_for_path,
    _is_embeddable_path,
    _iter_form_downloads,
    _related_form_downloads_for_citations,
    _resolve_citation_document_path,
    _resolve_document_path,
    _selected_form_downloads,
)
from backend.cache_db import (
    create_conversation,
    delete_conversation,
    get_conversation_messages,
    get_conversation_owner,
    insert_activity_log,
    list_conversations_for_user,
    mark_activity_log_cached,
    rename_conversation,
    update_activity_log_feedback,
)
from backend.observability import (
    current_trace_id,
    environment_name,
    score_user_thumbs_down,
    trace_context,
    update_observation,
)
from backend.semantic_cache import store_semantic_cache
from backend.settings import get_bool_env, get_env

logger = logging.getLogger("uvicorn.error")


def _truncate(value: object, limit: int = 300) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    if limit <= 3:
        return "." * max(0, limit)
    return f"{text[: limit - 3].rstrip()}..."


def _record_chat_activity(
    *,
    status: str,
    conversation_id: str,
    question: str,
    response_time_seconds: float,
    user_email: str = "",
    user_name: str = "",
    answer: str = "",
    answer_source: str = "",
    citations: list[CitationResponse] | None = None,
    form_downloads: list[FormDownloadResponse] | None = None,
    error: object = "",
    feedback_token: str = "",
    trace_id: str = "",
    cache_question: str = "",
    cache_citations: list[dict[str, object]] | None = None,
    cache_selected_forms: list[str] | None = None,
) -> int | None:
    citation_items = citations or []
    source_names = []
    for citation in citation_items:
        if citation.source and citation.source not in source_names:
            source_names.append(citation.source)
        if len(source_names) >= 3:
            break
    details: dict[str, object] = {
        "conversation_id": conversation_id,
        "user_email": user_email,
        "user_name": user_name,
        "question": question.strip(),
        "answer": answer.strip(),
        "answer_preview": _truncate(answer),
        "answer_source": answer_source,
        "citation_count": len(citation_items),
        "citation_sources": source_names,
        "form_count": len(form_downloads or []),
        "response_time_seconds": round(response_time_seconds, 3),
    }
    if feedback_token:
        details["feedback_token"] = feedback_token
    if trace_id:
        details["trace_id"] = trace_id
    if error:
        details["error"] = _truncate(error)
    if answer_source == "model" and cache_citations:
        details["cache_payload"] = {
            "question": cache_question,
            "citations": cache_citations,
            "selected_forms": cache_selected_forms or [],
        }
    try:
        return insert_activity_log(
            event_type="chat",
            action="query",
            status=status,
            summary=_truncate(question, 180),
            details=details,
        )
    except Exception as log_error:
        logger.warning("[activity-log] failed to save chat log: %s", log_error)
        return None


def _query_error_detail(
    *,
    message: str,
    conversation_id: str,
    feedback_id: int | None,
    feedback_token: str,
) -> dict[str, object]:
    detail: dict[str, object] = {
        "message": message,
        "conversation_id": conversation_id,
    }
    if feedback_id is not None:
        detail["feedback_id"] = feedback_id
        detail["feedback_token"] = feedback_token
    return detail


@app.get("/health")
def health_check() -> dict[str, str]:
    # Probe sederhana untuk mengecek backend hidup.
    return {"status": "ok"}


@app.get("/api/config", response_model=PublicConfigResponse)
def public_config() -> PublicConfigResponse:
    # Config frontend yang aman dibuka ke browser -- harus tetap publik (tanpa
    # login) karena frontend butuh google_client_id ini untuk merender tombol
    # Google Sign-In sebelum user login.
    return PublicConfigResponse(
        typing_animation_enabled=get_bool_env("TYPING_ANIMATION_ENABLED", False),
        google_client_id=get_env("GOOGLE_CLIENT_ID", ""),
    )


@app.post("/query", response_model=QueryResponse)
def query_knowledge_base(
    payload: QueryRequest,
    authorization: str = Header(default=""),
) -> QueryResponse:
    # Jawab query chat dengan citation dan form pilihan AI.
    from researcher_crew.main import ModelGenerationError, run_knowledge_crew

    user = _require_user(authorization)
    request_started = time.perf_counter()
    conversation_id = _clean_conversation_id(payload.conversation_id)
    owner_id = get_conversation_owner(conversation_id)
    if owner_id is not None and owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="This conversation does not belong to you.")
    if owner_id is None:
        create_conversation(conversation_id, user["id"], title=payload.question)
    logger.info('[chat:%s] POST /query | "%s"', conversation_id, payload.question)
    conversation_context = _get_conversation_context(conversation_id)
    logger.debug(
        "[chat:%s] Conversation context loaded (%s characters)",
        conversation_id,
        len(conversation_context),
    )
    available_forms = _iter_form_downloads()
    logger.debug(
        "[chat:%s] Form catalog loaded (%s items)",
        conversation_id,
        len(available_forms),
    )
    trace_metadata: dict[str, object] = {
        "route": "/query",
        "feature": "chat",
        "environment": environment_name(),
        "conversation_context_chars": len(conversation_context),
        "available_form_count": len(available_forms),
    }
    feedback_token = secrets.token_urlsafe(32)
    with trace_context(
        name="chat-query",
        session_id=conversation_id,
        input=payload.question,
        metadata=trace_metadata,
        tags=["capstone", "rag", "chat", environment_name()],
    ) as trace:
        try:
            answer, raw_citations, selected_form_names, answer_source, standalone_question = run_knowledge_crew(
                payload.question,
                conversation_context,
                available_forms=_form_catalog_entries(available_forms),
                trace_id=f"chat:{conversation_id}",
            )
        except ModelGenerationError as error:
            logger.exception("[chat:%s] Request failed", conversation_id)
            activity_log_id = _record_chat_activity(
                status="error",
                conversation_id=conversation_id,
                question=payload.question,
                response_time_seconds=time.perf_counter() - request_started,
                user_email=str(user["email"]),
                user_name=str(user["name"]),
                answer_source="fallback",
                error=error,
                feedback_token=feedback_token,
                trace_id=current_trace_id(),
            )
            update_observation(
                trace,
                metadata={
                    **trace_metadata,
                    "status": "error",
                    "response_time_seconds": round(time.perf_counter() - request_started, 3),
                },
                error=error,
            )
            raise HTTPException(
                status_code=502,
                detail=_query_error_detail(
                    message=str(error),
                    conversation_id=conversation_id,
                    feedback_id=activity_log_id,
                    feedback_token=feedback_token,
                ),
            ) from error
        except Exception as error:
            logger.exception("[chat:%s] Request failed", conversation_id)
            activity_log_id = _record_chat_activity(
                status="error",
                conversation_id=conversation_id,
                question=payload.question,
                response_time_seconds=time.perf_counter() - request_started,
                user_email=str(user["email"]),
                user_name=str(user["name"]),
                answer_source="fallback",
                error=error,
                feedback_token=feedback_token,
                trace_id=current_trace_id(),
            )
            update_observation(
                trace,
                metadata={
                    **trace_metadata,
                    "status": "error",
                    "response_time_seconds": round(time.perf_counter() - request_started, 3),
                },
                error=error,
            )
            raise HTTPException(
                status_code=500,
                detail=_query_error_detail(
                    message="Request failed to process.",
                    conversation_id=conversation_id,
                    feedback_id=activity_log_id,
                    feedback_token=feedback_token,
                ),
            ) from error
        _append_conversation_turn(conversation_id, payload.question, answer)
        logger.debug("[chat:%s] Conversation history saved", conversation_id)
        citations = [
            CitationResponse(
                **citation,
                download_url=_citation_download_url(str(citation["source"])),
            )
            for citation in raw_citations
        ]
        form_downloads: list[FormDownloadResponse] = []
        if _answer_has_supported_form_context(answer):
            selected_downloads = _selected_form_downloads(selected_form_names, available_forms)
            related_downloads = _related_form_downloads_for_citations(
                question=payload.question,
                answer=answer,
                citations=raw_citations,
                forms=available_forms,
            )
            form_downloads = []
            seen_form_urls: set[str] = set()
            for form_download in [*selected_downloads, *related_downloads]:
                if form_download.download_url in seen_form_urls:
                    continue
                form_downloads.append(form_download)
                seen_form_urls.add(form_download.download_url)
        response_time_seconds = time.perf_counter() - request_started
        logger.debug(
            "[chat:%s] Request completed in %.2fs, citation=%s, form=%s",
            conversation_id,
            response_time_seconds,
            len(citations),
            len(form_downloads),
        )
        activity_log_id = _record_chat_activity(
            status="success",
            conversation_id=conversation_id,
            question=payload.question,
            user_email=str(user["email"]),
            user_name=str(user["name"]),
            answer=answer,
            answer_source=answer_source,
            citations=citations,
            form_downloads=form_downloads,
            response_time_seconds=response_time_seconds,
            feedback_token=feedback_token,
            trace_id=current_trace_id(),
            cache_question=standalone_question,
            cache_citations=raw_citations,
            cache_selected_forms=selected_form_names,
        )
        try:
            from backend.preprocessing.vectorstore import get_active_index_name

            active_index = get_active_index_name()
        except Exception:
            active_index = ""
        update_observation(
            trace,
            output=answer,
            metadata={
                **trace_metadata,
                "status": "success",
                "answer_source": answer_source,
                "citation_count": len(citations),
                "selected_form_count": len(form_downloads),
                "active_index": active_index,
                "response_time_seconds": round(response_time_seconds, 3),
            },
        )
        return QueryResponse(
            answer=answer,
            citations=citations,
            form_downloads=form_downloads,
            conversation_id=conversation_id,
            answer_source=answer_source,
            feedback_id=activity_log_id,
            feedback_token=feedback_token if activity_log_id is not None else None,
        )


@app.post("/api/feedback", response_model=FeedbackResponse)
def submit_chat_feedback(
    payload: FeedbackPayload,
    authorization: str = Header(default=""),
) -> FeedbackResponse:
    # Simpan feedback user: thumbs_down -> log + Langfuse score, thumbs_up -> log + commit ke semantic cache.
    _require_user(authorization)
    clean_conversation_id = payload.conversation_id.strip()
    clean_reason = (payload.reason or "").strip()
    if payload.rating == "thumbs_down" and len(clean_reason) < 5:
        raise HTTPException(status_code=422, detail="Reason must be at least 5 characters.")

    updated_log = update_activity_log_feedback(
        log_id=payload.feedback_id,
        feedback_token=payload.feedback_token,
        conversation_id=clean_conversation_id,
        rating=payload.rating,
        reason=clean_reason,
    )
    if updated_log is None:
        raise HTTPException(status_code=404, detail="Feedback target not found.")

    details = updated_log.get("details") or {}
    feedback = details.get("feedback") if isinstance(details, dict) else {}
    if not isinstance(feedback, dict):
        feedback = {}

    if payload.rating == "thumbs_down":
        score_user_thumbs_down(
            trace_id=str(details.get("trace_id") or ""),
            feedback_id=payload.feedback_id,
            reason=clean_reason,
            conversation_id=clean_conversation_id,
        )
    elif payload.rating == "thumbs_up":
        cache_payload = details.get("cache_payload") if isinstance(details, dict) else None
        already_cached = bool(details.get("cached_entry_id"))
        if isinstance(cache_payload, dict) and not already_cached:
            entry_id = store_semantic_cache(
                str(cache_payload.get("question") or ""),
                str(details.get("answer") or ""),
                cache_payload.get("citations") or [],
                cache_payload.get("selected_forms") or [],
                trace_id=str(details.get("trace_id") or ""),
            )
            if entry_id:
                mark_activity_log_cached(payload.feedback_id, entry_id)

    return FeedbackResponse(message="Feedback recorded.", feedback=feedback)


@app.get("/api/faq", response_model=list[FAQItem])
def get_faq(authorization: str = Header(default="")) -> list[FAQItem]:
    # Kembalikan daftar FAQ tersimpan untuk user yang sudah login.
    _require_user(authorization)
    with FAQ_LOCK:
        return _load_faqs()


@app.get("/api/citations/{document_path:path}")
def download_citation_document(
    document_path: str,
    token: str = "",
    authorization: str = Header(default=""),
) -> FileResponse:
    # Buka dokumen yang boleh menjadi sumber citation untuk user yang login.
    # Link ini dibuka lewat <a href> biasa oleh browser (bukan fetch), jadi
    # terima token sesi via query param sebagai fallback dari header.
    _require_user_from_header_or_query(authorization, token)
    resolved_path = _resolve_citation_document_path(document_path)

    if not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="Document not found.")
    if not _is_embeddable_path(resolved_path):
        raise HTTPException(status_code=403, detail="Citation document is not public.")

    return FileResponse(
        path=resolved_path,
        filename=resolved_path.name,
        content_disposition_type="inline",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/documents/{document_path:path}")
def download_document(
    document_path: str,
    format: str = "pdf",
    token: str = "",
    authorization: str = Header(default=""),
) -> Response:
    # Unduh dokumen tersimpan untuk user yang login. Link ini juga dibuka
    # lewat <a href> biasa, jadi terima token sesi via query param sebagai
    # fallback dari header.
    _require_user_from_header_or_query(authorization, token)
    resolved_path = _resolve_document_path(document_path)

    if not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="Document not found.")
    document_kind = _document_kind_for_path(resolved_path)
    output_format = format.strip().lower()
    if output_format == "docx":
        if document_kind != "form" or resolved_path.suffix.lower() != ".pdf":
            raise HTTPException(status_code=400, detail="This document cannot be downloaded as Word.")
        docx_path = get_form_docx_template(resolved_path)
        return FileResponse(
            path=docx_path,
            filename=docx_path.name,
            media_type=DOCX_MIME,
            headers={"Cache-Control": "no-store"},
        )

    return FileResponse(
        path=resolved_path,
        filename=resolved_path.name,
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/conversations", response_model=list[ConversationSummary])
def list_conversations(
    limit: int = 30,
    offset: int = 0,
    authorization: str = Header(default=""),
) -> list[ConversationSummary]:
    # Daftar percakapan milik user yang login, terbaru dulu, untuk sidebar chat.
    user = _require_user(authorization)
    return [
        ConversationSummary(**item)
        for item in list_conversations_for_user(user["id"], limit=limit, offset=offset)
    ]


@app.get("/api/conversations/{conversation_id}/messages", response_model=ConversationMessagesResponse)
def get_conversation(
    conversation_id: str,
    authorization: str = Header(default=""),
) -> ConversationMessagesResponse:
    # Buka kembali satu percakapan lama milik user yang login.
    user = _require_user(authorization)
    owner_id = get_conversation_owner(conversation_id)
    if owner_id is None or owner_id != user["id"]:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    messages = [ConversationMessage(**item) for item in get_conversation_messages(conversation_id)]
    return ConversationMessagesResponse(id=conversation_id, messages=messages)


@app.patch("/api/conversations/{conversation_id}", response_model=MessageResponse)
def rename_conversation_title(
    conversation_id: str,
    payload: ConversationRenamePayload,
    authorization: str = Header(default=""),
) -> MessageResponse:
    # Ganti judul satu percakapan milik user yang login.
    user = _require_user(authorization)
    owner_id = get_conversation_owner(conversation_id)
    if owner_id is None or owner_id != user["id"]:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    rename_conversation(conversation_id, payload.title)
    return MessageResponse(message="Conversation renamed.")


@app.delete("/api/conversations/{conversation_id}", response_model=MessageResponse)
def delete_conversation_item(
    conversation_id: str,
    authorization: str = Header(default=""),
) -> MessageResponse:
    # Hapus satu percakapan milik user yang login.
    user = _require_user(authorization)
    owner_id = get_conversation_owner(conversation_id)
    if owner_id is None or owner_id != user["id"]:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    delete_conversation(conversation_id)
    return MessageResponse(message="Conversation deleted.")


@app.get("/", response_class=FileResponse, include_in_schema=False)
def frontend_app() -> FileResponse:
    # Sajikan file index frontend untuk route root.
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Frontend bundle not found.")
    return FileResponse(index_file)
