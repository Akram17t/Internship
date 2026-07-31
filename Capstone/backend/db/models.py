from __future__ import annotations

"""SQLAlchemy ORM models for the PostgreSQL backend.

Mirrors the SQLite schema in backend/cache_db.py (schema `app`) plus a
simplified analytics schema (`analytics`) for the usage dashboard. This is a
reduced-scope implementation: no migration/audit/taxonomy-history schemas
from the full design doc.
"""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------
# app schema - operational tables (parity with backend/cache_db.py)
# --------------------------------------------------------------------------


class AppStateMeta(Base):
    __tablename__ = "app_state_meta"
    __table_args__ = {"schema": "app"}

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "app"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False, default="")
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_login_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AdminAccount(Base):
    __tablename__ = "admin_accounts"
    __table_args__ = {"schema": "app"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    password: Mapped[str] = mapped_column(String, nullable=False, default="")
    name: Mapped[str] = mapped_column(String, nullable=False, default="Admin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = {"schema": "app"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("app.users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_conversation_messages_role"),
        {"schema": "app"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("app.conversations.id", ondelete="CASCADE"), nullable=True
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    conversation: Mapped[Conversation | None] = relationship(back_populates="messages")


class SemanticCacheEntry(Base):
    __tablename__ = "semantic_cache_entries"
    __table_args__ = {"schema": "app"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_question: Mapped[str] = mapped_column(Text, nullable=False, default="")
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    citations_json: Mapped[dict | list] = mapped_column(JSONB, nullable=False, default=list)
    selected_forms_json: Mapped[dict | list] = mapped_column(JSONB, nullable=False, default=list)
    active_index: Mapped[str] = mapped_column(String, nullable=False)
    model_name: Mapped[str] = mapped_column(String, nullable=False)
    embed_model_name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ActivityLog(Base):
    __tablename__ = "activity_logs"
    __table_args__ = (
        CheckConstraint("event_type IN ('chat', 'document')", name="ck_activity_logs_event_type"),
        CheckConstraint("status IN ('success', 'error')", name="ck_activity_logs_status"),
        {"schema": "app"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False, default="")
    status: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    details_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FaqItem(Base):
    __tablename__ = "faq_items"
    __table_args__ = {"schema": "app"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False, default="")
    source_url: Mapped[str] = mapped_column(String, nullable=False, default="")
    suggested_query: Mapped[str] = mapped_column(Text, nullable=False, default="")
    citations_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    image_url: Mapped[str] = mapped_column(String, nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# --------------------------------------------------------------------------
# analytics schema - simplified (single interaction table + daily aggregate)
# --------------------------------------------------------------------------


class CanonicalInteraction(Base):
    __tablename__ = "canonical_interactions"
    __table_args__ = (
        UniqueConstraint("activity_log_id", name="uq_canonical_interactions_activity_log_id"),
        {"schema": "analytics"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    activity_log_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    pseudonymous_user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    response_status: Mapped[str] = mapped_column(String, nullable=False)
    answer_source: Mapped[str | None] = mapped_column(String, nullable=True)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    citation_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    form_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback_rating: Mapped[str | None] = mapped_column(String, nullable=True)
    topic_code: Mapped[str] = mapped_column(String, nullable=False, default="unclassified")
    topic_confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DailyTopicAggregate(Base):
    __tablename__ = "daily_topic_aggregates"
    __table_args__ = (
        UniqueConstraint(
            "bucket_date", "topic_code", name="uq_daily_topic_aggregates_bucket_topic"
        ),
        {"schema": "analytics"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    bucket_date: Mapped[date] = mapped_column(Date, nullable=False)
    topic_code: Mapped[str] = mapped_column(String, nullable=False)
    interaction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unique_user_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    negative_feedback_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_or_fallback_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
