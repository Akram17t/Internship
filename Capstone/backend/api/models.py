from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, description="Natural language question from the user.")
    conversation_id: str | None = Field(default=None, description="Client conversation identifier.")


class CitationResponse(BaseModel):
    id: int
    source: str
    page: int | None = None
    section: str | None = None
    chunk_id: int | None = None
    download_url: str | None = None


class FormDownloadResponse(BaseModel):
    name: str
    display_name: str
    download_url: str


class FlowchartScreenshotResponse(BaseModel):
    id: str
    title: str
    source: str
    page: int | None = None
    section: str = ""
    confidence: float = 0
    image_url: str


class QueryResponse(BaseModel):
    answer: str
    citations: list[CitationResponse] = Field(default_factory=list)
    form_downloads: list[FormDownloadResponse] = Field(default_factory=list)
    flowcharts: list[FlowchartScreenshotResponse] = Field(default_factory=list)
    conversation_id: str
    answer_source: Literal["model", "cache", "fallback"] = "model"
    feedback_id: int | None = None
    feedback_token: str | None = None


class FeedbackPayload(BaseModel):
    feedback_id: int = Field(..., ge=1)
    feedback_token: str = Field(..., min_length=16, max_length=256)
    conversation_id: str = Field(..., min_length=1, max_length=128)
    rating: Literal["thumbs_down"]
    reason: str = Field(..., min_length=5, max_length=500)


class FeedbackResponse(BaseModel):
    message: str
    feedback: dict[str, Any]


class PublicConfigResponse(BaseModel):
    typing_animation_enabled: bool


class FAQItem(BaseModel):
    id: str
    question: str
    answer: str
    source: str = ""
    source_url: str = ""
    suggested_query: str
    citations: list[CitationResponse] = Field(default_factory=list)
    image_url: str = ""
    updated_at: str | None = None


class AdminFAQPayload(BaseModel):
    question: str = Field(..., min_length=3)


class AdminFAQResponse(BaseModel):
    message: str
    item: FAQItem | None = None


class AdminLoginPayload(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=1)


class AdminLoginResponse(BaseModel):
    email: str
    name: str
    token: str
    expires_at: str


class AdminCreatePayload(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=1)
    name: str = Field(default="Admin", min_length=1)


class AdminAccountResponse(BaseModel):
    email: str
    name: str


class LibraryItem(BaseModel):
    name: str
    relative_path: str
    display_name: str
    doc_type: str
    document_kind: str
    is_embeddable: bool
    size_bytes: int
    updated_at: str
    download_url: str


class ActivityLogItem(BaseModel):
    id: int
    event_type: Literal["chat", "document"]
    action: str = ""
    status: Literal["success", "error"]
    summary: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ActivityLogSummaryResponse(BaseModel):
    total_chat: int = 0
    total_sessions: int = 0
    average_chat_per_session: float = 0
    fallback_or_error: int = 0
    negative_feedback: int = 0
    negative_feedback_rate: float = 0


class ActivityLogSessionItem(BaseModel):
    conversation_id: str
    question_count: int = 0
    fallback_or_error: int = 0
    first_at: str = ""
    last_at: str = ""
    first_question: str = ""
    latest_question: str = ""
    latest_status: Literal["success", "error"] = "success"


class AdminDocumentPayload(BaseModel):
    filename: str = Field(..., min_length=1)
    content_base64: str = Field(..., min_length=1)
    replace_path: str | None = None


class AdminDocumentResponse(BaseModel):
    message: str
    requires_reindex: bool = False
    item: LibraryItem | None = None


class AdminReindexResponse(BaseModel):
    message: str
