"""Initial user and chat-log tables agreed in the team DB plan, plus star reference data."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utc_now():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

class ChatLog(Base):
    __tablename__ = "chat_logs"
    __table_args__ = (Index("ix_chat_logs_user_created", "user_id", "created_at", "id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

# Star tables are filled by scripts/namuwiki/load.py, not by the app.
STAR_SOURCE_NOTE = (
    "Namu Wiki (https://namu.wiki) documents, cleaned and split. "
    "CC BY-NC-SA 2.0 KR, non-commercial use only. See docs/DATA.md."
)

class StarProfile(Base):
    __tablename__ = "star_profiles"
    __table_args__ = {"comment": STAR_SOURCE_NOTE}
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # person | group
    group_name: Mapped[Optional[str]] = mapped_column(Text)
    gender: Mapped[Optional[str]] = mapped_column(String(1))  # M | F
    birth_year: Mapped[Optional[int]] = mapped_column(SmallInteger)
    debut_year: Mapped[Optional[int]] = mapped_column(SmallInteger)
    birthplace: Mapped[Optional[str]] = mapped_column(Text)
    agency: Mapped[Optional[str]] = mapped_column(Text)
    height_cm: Mapped[Optional[float]] = mapped_column(Float)
    aliases: Mapped[str] = mapped_column(Text, default="", nullable=False)  # one per line
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

class StarChunk(Base):
    __tablename__ = "star_chunks"
    __table_args__ = (
        UniqueConstraint("profile_id", "chunk_index", name="uq_star_chunks_profile_index"),
        {"comment": STAR_SOURCE_NOTE},
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("star_profiles.id", ondelete="CASCADE"), nullable=False
    )
    section: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
