from __future__ import annotations

import logging
import secrets
import time

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response

from backend.api.cache_store import _append_conversation_turn, _clean_conversation_id, _get_conversation_context, _load_faqs
from backend.api.core import FAQ_LOCK, FRONTEND_DIR, app
from backend.api.faq_service import get_pinned_image_file, _pinned_faq_items
from backend.api.forms_service import (
    DOCX_MIME,
    get_form_docx_template,
)
from backend.api.flowchart_service import (
    find_flowcharts_for_citations,
    get_flowchart_image,
)
from backend.api.models import (
    CitationResponse,
    FAQItem,
    FeedbackPayload,
    FeedbackResponse,
    FlowchartScreenshotResponse,
    FormDownloadResponse,
    PublicConfigResponse,
    QueryRequest,
    QueryResponse,
)
from backend.api.storage import (
    _answer_has_supported_form_context,
    _available_form_catalog,
    _citation_download_url,
    _document_kind_for_path,
    _is_embeddable_path,
    _iter_form_downloads,
    _resolve_citation_document_path,
    _resolve_document_path,
    _selected_form_downloads,
)
from backend.cache_db import insert_activity_log, update_activity_log_feedback
from backend.observability import (
    current_trace_id,
    environment_name,
    score_user_thumbs_down,
    trace_context,
    update_observation,
)
from backend.settings import get_bool_env

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
    answer: str = "",
    answer_source: str = "",
    citations: list[CitationResponse] | None = None,
    form_downloads: list[FormDownloadResponse] | None = None,
    flowcharts: list[FlowchartScreenshotResponse] | None = None,
    error: object = "",
    feedback_token: str = "",
    trace_id: str = "",
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
        "question": question.strip(),
        "answer": answer.strip(),
        "answer_preview": _truncate(answer),
        "answer_source": answer_source,
        "citation_count": len(citation_items),
        "citation_sources": source_names,
        "form_count": len(form_downloads or []),
        "flowchart_count": len(flowcharts or []),
        "response_time_seconds": round(response_time_seconds, 3),
    }
    if feedback_token:
        details["feedback_token"] = feedback_token
    if trace_id:
        details["trace_id"] = trace_id
    if error:
        details["error"] = _truncate(error)
    try:
        return insert_activity_log(
            event_type="chat",
            action="query",
            status=status,
            summary=_truncate(question, 180),
            details=details,
        )
    except Exception as log_error:
        logger.warning("[activity-log] gagal menyimpan log chat: %s", log_error)
        return None


@app.get("/health")
def health_check() -> dict[str, str]:
    # Probe sederhana untuk mengecek backend hidup.
    return {"status": "ok"}


@app.get("/api/config", response_model=PublicConfigResponse)
def public_config() -> PublicConfigResponse:
    # Config frontend yang aman dibuka ke browser.
    return PublicConfigResponse(
        typing_animation_enabled=get_bool_env("TYPING_ANIMATION_ENABLED", True),
    )


@app.post("/query", response_model=QueryResponse)
def query_knowledge_base(payload: QueryRequest) -> QueryResponse:
    # Jawab query chat dengan citation dan form pilihan AI.
    from researcher_crew.main import ModelGenerationError, run_knowledge_crew

    request_started = time.perf_counter()
    conversation_id = _clean_conversation_id(payload.conversation_id)
    logger.info('[chat:%s] POST /query | "%s"', conversation_id, payload.question)
    conversation_context = _get_conversation_context(conversation_id)
    logger.debug(
        "[chat:%s] Context percakapan dimuat (%s karakter)",
        conversation_id,
        len(conversation_context),
    )
    available_forms = _iter_form_downloads()
    logger.debug(
        "[chat:%s] Katalog form dimuat (%s item)",
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
    with trace_context(
        name="chat-query",
        session_id=conversation_id,
        input=payload.question,
        metadata=trace_metadata,
        tags=["capstone", "rag", "chat", environment_name()],
    ) as trace:
        try:
            answer, raw_citations, selected_form_names, answer_source = run_knowledge_crew(
                payload.question,
                conversation_context,
                available_forms=_available_form_catalog(available_forms),
                trace_id=f"chat:{conversation_id}",
            )
        except ModelGenerationError as error:
            logger.exception("[chat:%s] Request gagal", conversation_id)
            _record_chat_activity(
                status="error",
                conversation_id=conversation_id,
                question=payload.question,
                response_time_seconds=time.perf_counter() - request_started,
                error=error,
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
            raise HTTPException(status_code=502, detail=str(error)) from error
        except Exception as error:
            logger.exception("[chat:%s] Request gagal", conversation_id)
            _record_chat_activity(
                status="error",
                conversation_id=conversation_id,
                question=payload.question,
                response_time_seconds=time.perf_counter() - request_started,
                error=error,
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
            raise
        _append_conversation_turn(conversation_id, payload.question, answer)
        logger.debug("[chat:%s] Riwayat percakapan tersimpan", conversation_id)
        citations = [
            CitationResponse(
                **citation,
                download_url=_citation_download_url(str(citation["source"])),
            )
            for citation in raw_citations
        ]
        form_downloads: list[FormDownloadResponse] = []
        if _answer_has_supported_form_context(answer):
            form_downloads = _selected_form_downloads(selected_form_names, available_forms)
        flowcharts = [
            FlowchartScreenshotResponse(**flowchart)
            for flowchart in find_flowcharts_for_citations(raw_citations)
        ]
        response_time_seconds = time.perf_counter() - request_started
        logger.debug(
            "[chat:%s] Request selesai dalam %.2fs, citation=%s, form=%s, flowchart=%s",
            conversation_id,
            response_time_seconds,
            len(citations),
            len(form_downloads),
            len(flowcharts),
        )
        feedback_token = secrets.token_urlsafe(32)
        activity_log_id = _record_chat_activity(
            status="success",
            conversation_id=conversation_id,
            question=payload.question,
            answer=answer,
            answer_source=answer_source,
            citations=citations,
            form_downloads=form_downloads,
            flowcharts=flowcharts,
            response_time_seconds=response_time_seconds,
            feedback_token=feedback_token,
            trace_id=current_trace_id(),
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
                "flowchart_count": len(flowcharts),
                "active_index": active_index,
                "response_time_seconds": round(response_time_seconds, 3),
            },
        )
        return QueryResponse(
            answer=answer,
            citations=citations,
            form_downloads=form_downloads,
            flowcharts=flowcharts,
            conversation_id=conversation_id,
            answer_source=answer_source,
            feedback_id=activity_log_id,
            feedback_token=feedback_token if activity_log_id is not None else None,
        )


@app.post("/api/feedback", response_model=FeedbackResponse)
def submit_chat_feedback(payload: FeedbackPayload) -> FeedbackResponse:
    # Simpan feedback negatif user untuk log lokal dan Langfuse score.
    clean_reason = payload.reason.strip()
    clean_conversation_id = payload.conversation_id.strip()
    if len(clean_reason) < 5:
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
    score_user_thumbs_down(
        trace_id=str(details.get("trace_id") or ""),
        feedback_id=payload.feedback_id,
        reason=clean_reason,
        conversation_id=clean_conversation_id,
    )
    return FeedbackResponse(message="Feedback recorded.", feedback=feedback)


@app.get("/api/flowcharts/{flowchart_id}")
def flowchart_screenshot(flowchart_id: str) -> Response:
    image = get_flowchart_image(flowchart_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Flowchart image not found.")
    content, media_type = image
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@app.get("/api/faq", response_model=list[FAQItem])
def get_faq() -> list[FAQItem]:
    # Kembalikan FAQ pinned lalu FAQ tersimpan.
    with FAQ_LOCK:
        stored = _load_faqs()
    return [*_pinned_faq_items(), *stored]


@app.get("/api/faq-image/{filename}")
def get_faq_image(filename: str) -> FileResponse:
    # Sajikan gambar organogram upload dari storage persisten.
    try:
        image_path = get_pinned_image_file(filename)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="FAQ image not found.") from error
    return FileResponse(
        path=image_path,
        filename=image_path.name,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@app.get("/api/citations/{document_path:path}")
def download_citation_document(document_path: str) -> FileResponse:
    # Unduh dokumen yang memang boleh menjadi sumber citation untuk guest.
    resolved_path = _resolve_citation_document_path(document_path)

    if not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="Document not found.")
    if not _is_embeddable_path(resolved_path):
        raise HTTPException(status_code=403, detail="Citation document is not public.")

    return FileResponse(
        path=resolved_path,
        filename=resolved_path.name,
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/documents/{document_path:path}")
def download_document(
    document_path: str,
    format: str = "pdf",
) -> Response:
    # Unduh dokumen tersimpan untuk library publik.
    resolved_path = _resolve_document_path(document_path)

    if not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="Document not found.")
    document_kind = _document_kind_for_path(resolved_path)
    output_format = format.strip().lower()
    if output_format == "docx":
        if document_kind != "form" or resolved_path.suffix.lower() != ".pdf":
            raise HTTPException(status_code=400, detail="Dokumen ini tidak bisa diunduh sebagai Word.")
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


@app.get("/", response_class=FileResponse, include_in_schema=False)
def frontend_app() -> FileResponse:
    # Sajikan file index frontend untuk route root.
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Frontend bundle not found.")
    return FileResponse(index_file)
