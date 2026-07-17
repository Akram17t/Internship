from __future__ import annotations

import json
import logging
import time
from urllib.parse import quote

from fastapi import Header, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import ValidationError

from backend.api.auth import _require_admin
from backend.api.cache_store import _append_conversation_turn, _clean_conversation_id, _get_conversation_context, _load_faqs
from backend.api.core import FAQ_LOCK, FRONTEND_DIR, app
from backend.api.faq_service import _pinned_faq_items
from backend.api.forms_service import (
    DOCX_MIME,
    PDF_MIME,
    _fill_form_placeholders,
    _resolve_form_path,
    _unique_form_fields,
    fill_docx_schema_form,
    filled_pdf_to_docx,
    get_form_schema,
    get_word_template_docx,
    has_schema_form,
)
from backend.api.flowchart_service import (
    find_flowcharts_for_citations,
    get_flowchart_image,
)
from backend.api.models import (
    CitationResponse,
    FAQItem,
    FlowchartScreenshotResponse,
    FormDownloadResponse,
    FormFillPayload,
    FormSchemaResponse,
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
from backend.cache_db import insert_activity_log
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
) -> None:
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
    if error:
        details["error"] = _truncate(error)
    try:
        insert_activity_log(
            event_type="chat",
            action="query",
            status=status,
            summary=_truncate(question, 180),
            details=details,
        )
    except Exception as log_error:
        logger.warning("[activity-log] gagal menyimpan log chat: %s", log_error)


def _filled_form_filename(
    path: str,
    values: dict[str, str | bool],
    output_format: str = "pdf",
) -> str:
    resolved_path = _resolve_form_path(path)
    first_value = next(
        (
            str(value).strip()
            for value in values.values()
            if isinstance(value, str) and value.strip()
        ),
        "",
    )
    suffix = f" - {first_value}" if first_value else ""
    extension = "docx" if output_format == "docx" else "pdf"
    return f"{resolved_path.stem}{suffix}.{extension}"


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
    from researcher_crew.main import OllamaGenerationError, run_knowledge_crew

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
    try:
        answer, raw_citations, selected_form_names, answer_source = run_knowledge_crew(
            payload.question,
            conversation_context,
            available_forms=_available_form_catalog(available_forms),
            trace_id=f"chat:{conversation_id}",
        )
    except OllamaGenerationError as error:
        logger.exception("[chat:%s] Request gagal", conversation_id)
        _record_chat_activity(
            status="error",
            conversation_id=conversation_id,
            question=payload.question,
            response_time_seconds=time.perf_counter() - request_started,
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
    logger.debug(
        "[chat:%s] Request selesai dalam %.2fs, citation=%s, form=%s, flowchart=%s",
        conversation_id,
        time.perf_counter() - request_started,
        len(citations),
        len(form_downloads),
        len(flowcharts),
    )
    _record_chat_activity(
        status="success",
        conversation_id=conversation_id,
        question=payload.question,
        answer=answer,
        answer_source=answer_source,
        citations=citations,
        form_downloads=form_downloads,
        flowcharts=flowcharts,
        response_time_seconds=time.perf_counter() - request_started,
    )
    return QueryResponse(
        answer=answer,
        citations=citations,
        form_downloads=form_downloads,
        flowcharts=flowcharts,
        conversation_id=conversation_id,
        answer_source=answer_source,
    )


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
    authorization: str = Header(default=""),
) -> Response:
    # Unduh dokumen tersimpan, dengan file non-form dibatasi untuk admin.
    resolved_path = _resolve_document_path(document_path)

    if not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="Document not found.")
    document_kind = _document_kind_for_path(resolved_path)
    if document_kind != "form":
        _require_admin(authorization)
    output_format = format.strip().lower()
    if output_format == "docx":
        if document_kind != "form" or resolved_path.suffix.lower() != ".pdf":
            raise HTTPException(status_code=400, detail="Dokumen ini tidak bisa diunduh sebagai Word.")
        content = get_word_template_docx(resolved_path)
        filename = f"{resolved_path.stem}.docx"
        return Response(
            content=content,
            media_type=DOCX_MIME,
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            },
        )

    return FileResponse(
        path=resolved_path,
        filename=resolved_path.name,
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/forms/fields")
def form_fields(path: str) -> dict[str, object]:
    # Tampilkan field input sederhana yang terdeteksi di template form.
    resolved_path = _resolve_form_path(path)
    return {"fields": _unique_form_fields(resolved_path)}


@app.get("/api/forms/schema", response_model=FormSchemaResponse)
def form_schema(path: str) -> FormSchemaResponse:
    return FormSchemaResponse(**get_form_schema(path))


@app.post("/api/forms/fill")
async def fill_form(request: Request) -> Response:
    # Isi template form di memory lalu kembalikan file sesuai format pilihan.
    content_type = request.headers.get("content-type", "").lower()
    if "multipart/form-data" in content_type:
        form = await request.form()
        raw_payload = form.get("payload")
        if raw_payload is None:
            raise HTTPException(status_code=422, detail="Payload form tidak ditemukan.")

        try:
            payload = FormFillPayload.model_validate(json.loads(str(raw_payload)))
        except (ValidationError, json.JSONDecodeError) as error:
            raise HTTPException(status_code=422, detail="Payload form tidak valid.") from error

        resolved_path = _resolve_form_path(payload.path)
        signature_files: dict[str, dict[str, object]] = {}
        for key, value in form.multi_items():
            if key == "payload" or not hasattr(value, "filename"):
                continue
            content = await value.read()
            signature_files[key] = {
                "filename": value.filename or "",
                "content_type": value.content_type or "",
                "content": content,
            }
            await value.close()
        if has_schema_form(resolved_path):
            if payload.output_format != "docx":
                raise HTTPException(
                    status_code=422,
                    detail="PDF terisi belum didukung untuk form schema. Gunakan format Word.",
                )
            content = fill_docx_schema_form(resolved_path, payload.values, signature_files)
            filename = _filled_form_filename(payload.path, payload.values, "docx")
            return Response(
                content=content,
                media_type=DOCX_MIME,
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
                },
            )
        else:
            pdf_content = _fill_form_placeholders(
                resolved_path,
                {
                    key: str(value).strip()
                    for key, value in payload.values.items()
                    if isinstance(value, str)
                },
            )
    else:
        try:
            payload = FormFillPayload.model_validate(await request.json())
        except (ValidationError, json.JSONDecodeError) as error:
            raise HTTPException(status_code=422, detail="Payload form tidak valid.") from error

        resolved_path = _resolve_form_path(payload.path)
        if has_schema_form(resolved_path):
            if payload.output_format != "docx":
                raise HTTPException(
                    status_code=422,
                    detail="PDF terisi belum didukung untuk form schema. Gunakan format Word.",
                )
            content = fill_docx_schema_form(resolved_path, payload.values, {})
            media_type = DOCX_MIME
            filename = _filled_form_filename(payload.path, payload.values, "docx")
            return Response(
                content=content,
                media_type=media_type,
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
                },
            )
        else:
            pdf_content = _fill_form_placeholders(
                resolved_path,
                {
                    key: str(value).strip()
                    for key, value in payload.values.items()
                    if isinstance(value, str)
                },
            )
    output_format = payload.output_format
    if output_format == "docx":
        content = filled_pdf_to_docx(pdf_content)
        media_type = DOCX_MIME
    else:
        content = pdf_content
        media_type = PDF_MIME

    filename = _filled_form_filename(payload.path, payload.values, output_format)
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
        },
    )


@app.get("/", response_class=FileResponse, include_in_schema=False)
def frontend_app() -> FileResponse:
    # Sajikan file index frontend untuk route root.
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Frontend bundle not found.")
    return FileResponse(index_file)
