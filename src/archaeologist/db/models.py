"""SQLAlchemy ORM models for SessionArchaeologist."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    total_turns: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens_est: Mapped[int] = mapped_column(Integer, default=0)
    manifest: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default="imported"
    )  # imported, chunked, extracting, extracted, synthesizing, synthesized, refining

    # Subagent support
    parent_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=True
    )
    session_type: Mapped[str] = mapped_column(String(20), default="main")  # main, subagent
    agent_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # Explore, Plan, etc.
    agent_description: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    turns: Mapped[list["Turn"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    narratives: Mapped[list["Narrative"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    subagents: Mapped[list["Session"]] = relationship("Session", back_populates="parent_session")
    parent_session: Mapped["Session | None"] = relationship(
        "Session", remote_side=[id], back_populates="subagents"
    )


class Turn(Base):
    __tablename__ = "turns"
    __table_args__ = (
        Index("ix_turns_session_turn", "session_id", "turn_index"),
        Index("ix_turns_session_error", "session_id", "is_error"),
        Index("ix_turns_session_compact", "session_id", "is_compact_boundary"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user, assistant, system
    content_text: Mapped[str] = mapped_column(Text, default="")
    tool_calls: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_compact_boundary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_error: Mapped[bool] = mapped_column(Boolean, default=False)
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    raw_jsonl_line: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Extra fields from actual JSONL format
    message_uuid: Mapped[str | None] = mapped_column(String(100), nullable=True)
    parent_uuid: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_sidechain: Mapped[bool] = mapped_column(Boolean, default=False)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    token_usage: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    has_thinking: Mapped[bool] = mapped_column(Boolean, default=False)

    session: Mapped["Session"] = relationship(back_populates="turns")


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (Index("ix_chunks_session_index", "session_id", "chunk_index"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_turn: Mapped[int] = mapped_column(Integer, nullable=False)
    end_turn: Mapped[int] = mapped_column(Integer, nullable=False)
    overlap_start_turn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)
    hot_zone_count: Mapped[int] = mapped_column(Integer, default=0)
    contains_compact_boundary: Mapped[bool] = mapped_column(Boolean, default=False)
    extraction_status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending, processing, done, failed
    extraction_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    extraction_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    extraction_cost_est: Mapped[float | None] = mapped_column(Float, nullable=True)
    artifact_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    session: Mapped["Session"] = relationship(back_populates="chunks")


class Narrative(Base):
    __tablename__ = "narratives"
    __table_args__ = (Index("ix_narratives_session_rev", "session_id", "revision"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_md: Mapped[str] = mapped_column(Text, default="")
    synthesis_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    annotations_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    session: Mapped["Session"] = relationship(back_populates="narratives")
    annotations: Mapped[list["Annotation"]] = relationship(back_populates="narrative", cascade="all, delete-orphan")


class Annotation(Base):
    __tablename__ = "annotations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    narrative_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("narratives.id", ondelete="CASCADE"))
    section_path: Mapped[str] = mapped_column(String(500), nullable=False)
    annotation_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # correction, injection, needs_detail, tone_change, verified
    content: Mapped[str] = mapped_column(Text, default="")
    source_chunk_ids: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    narrative: Mapped["Narrative"] = relationship(back_populates="annotations")
