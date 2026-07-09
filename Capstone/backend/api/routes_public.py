from __future__ import annotations

import logging
import time
from urllib.parse import quote

from fastapi import Header, HTTPException
from fastapi.responses import FileResponse, Response

from backend.api.auth import _require_admin
from backend.api.cache_store import _append_conversation_turn, _clean_conversation_id, _get_conversation_context, _load_faqs
from backend.api.core import FAQ_LOCK, FRONTEND_DIR, app
from backend.api.faq_service import _pinned_faq_items
from backend.api.forms_service import XLSX_MIME, _fill_form_placeholders, _resolve_form_path, _unique_form_fields
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
    QueryRequest,
    QueryResponse,
)
from backend.api.storage import (
    _answer_has_supported_form_context,
    _available_form_catalog,
    _document_kind_for_path,
    _iter_form_downloads,
    _resolve_document_path,
    _selected_form_downloads,
)

logger = logging.getLogger("uvicorn.error")


@app.get("/health")
def health_check() -> dict[str, str]:
    # Probe sederhana untuk mengecek backend hidup.
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query_knowledge_base(payload: QueryRequest) -> QueryResponse:
    # Jawab query chat dengan citation dan form pilihan AI.
    from researcher_crew.main import OllamaGenerationError, run_knowledge_crew

    request_started = time.perf_counter()
    conversation_id = _clean_conversation_id(payload.conversation_id)
    logger.debug("[chat:%s] Request baru diterima", conversation_id)
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
        answer, raw_citations, selected_form_names = run_knowledge_crew(
            payload.question,
            conversation_context,
            available_forms=_available_form_catalog(available_forms),
            trace_id=f"chat:{conversation_id}",
        )
    except OllamaGenerationError as error:
        logger.exception("[chat:%s] Request gagal", conversation_id)
        raise HTTPException(status_code=502, detail=str(error)) from error
    _append_conversation_turn(conversation_id, payload.question, answer)
    logger.debug("[chat:%s] Riwayat percakapan tersimpan", conversation_id)
    citations = [
        CitationResponse(
            **citation,
            download_url=f"/api/documents/{quote(str(citation['source']), safe='')}",
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
    return QueryResponse(
        answer=answer,
        citations=citations,
        form_downloads=form_downloads,
        flowcharts=flowcharts,
        conversation_id=conversation_id,
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


@app.get("/api/documents/{document_path:path}")
def download_document(
    document_path: str,
    authorization: str = Header(default=""),
) -> FileResponse:
    # Unduh dokumen tersimpan, dengan file non-form dibatasi untuk admin.
    resolved_path = _resolve_document_path(document_path)

    if not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="Document not found.")
    if _document_kind_for_path(resolved_path) != "form":
        _require_admin(authorization)

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


@app.post("/api/forms/fill")
def fill_form(payload: FormFillPayload) -> Response:
    # Isi template form di memory lalu kembalikan file xlsx hasilnya.
    resolved_path = _resolve_form_path(payload.path)
    content = _fill_form_placeholders(resolved_path, payload.values)
    nama = next(
        (v.strip() for v in payload.values.values() if v.strip()),
        "",
    )
    suffix = f" - {nama}" if nama else ""
    filename = f"{resolved_path.stem}{suffix}.xlsx"
    return Response(
        content=content,
        media_type=XLSX_MIME,
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
