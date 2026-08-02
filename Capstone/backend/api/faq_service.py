from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from backend.answer_policy import is_unsupported_answer, strip_trailing_unsupported_answer
from backend.api.models import AdminFAQPayload, CitationResponse, FAQItem
from backend.api.storage import _citation_download_url
from backend.observability import environment_name, trace_context


def _is_unusable_faq_answer(answer: str, citations: list[CitationResponse]) -> bool:
    # Tolak jawaban FAQ yang tidak punya evidence atau terlalu generik.
    normalized = " ".join(answer.lower().split())
    return not citations or is_unsupported_answer(answer) or "[nama perusahaan]" in normalized


def _build_faq_item(payload: AdminFAQPayload, faq_id: str | None = None) -> FAQItem:
    # Buat dan validasi satu entri FAQ dari pertanyaan.
    from researcher_crew.main import ModelGenerationError, run_faq_crew

    question = payload.question.strip()
    resolved_faq_id = faq_id or uuid.uuid4().hex
    try:
        with trace_context(
            name="faq-generate",
            session_id=resolved_faq_id,
            input=question,
            metadata={"feature": "faq", "environment": environment_name()},
            tags=["capstone", "rag", "faq", environment_name()],
        ):
            answer, raw_citations = run_faq_crew(question)
    except ModelGenerationError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    answer = strip_trailing_unsupported_answer(answer)
    citations = [
        CitationResponse(
            **citation,
            download_url=_citation_download_url(str(citation["source"])),
        )
        for citation in raw_citations
    ]
    if _is_unusable_faq_answer(answer, citations):
        raise HTTPException(
            status_code=422,
            detail=(
                "FAQ was not saved because there is no source from indexed documents. "
                "Try writing a more specific question or add a relevant document."
            ),
        )
    source = citations[0].source if citations else ""
    source_url = citations[0].download_url if citations else ""
    return FAQItem(
        id=resolved_faq_id,
        question=question,
        answer=answer,
        source=source,
        source_url=source_url or "",
        suggested_query=question,
        citations=citations,
        updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
