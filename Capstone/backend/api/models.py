from __future__ import annotations

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


class FlowchartNodeResponse(BaseModel):
    id: str
    type: str
    text: str
    confidence: float = 0


class FlowchartEdgeResponse(BaseModel):
    source: str
    target: str
    label: str = ""
    confidence: float = 0


class FlowchartDiagramResponse(BaseModel):
    id: str
    title: str
    source: str
    page: int | None = None
    section: str = ""
    confidence: float = 0
    nodes: list[FlowchartNodeResponse] = Field(default_factory=list)
    edges: list[FlowchartEdgeResponse] = Field(default_factory=list)


class QueryResponse(BaseModel):
    answer: str
    citations: list[CitationResponse] = Field(default_factory=list)
    form_downloads: list[FormDownloadResponse] = Field(default_factory=list)
    diagrams: list[FlowchartDiagramResponse] = Field(default_factory=list)
    conversation_id: str


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


class FormFillPayload(BaseModel):
    path: str = Field(..., min_length=1)
    values: dict[str, str] = Field(default_factory=dict)
