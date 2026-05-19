"""Database models — borrowers, calls, transcripts, promises-to-pay, audit log.

We use SQLAlchemy 2.0 async with asyncpg. Migrations live under
agent/alembic/ (run `alembic upgrade head` once Postgres is up).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


class Borrower(Base):
    __tablename__ = "borrowers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    preferred_language: Mapped[str] = mapped_column(String(8), default="hi-en")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    calls: Mapped[list["Call"]] = relationship(back_populates="borrower")


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    borrower_id: Mapped[str] = mapped_column(ForeignKey("borrowers.id"))
    plivo_call_uuid: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    ended_at: Mapped[Optional[datetime]] = mapped_column(default=None)
    outcome: Mapped[Optional[str]] = mapped_column(String(32), default=None)  # ptp/restructure/escalated/no_answer
    overdue_amount: Mapped[int] = mapped_column(Integer, default=0)
    days_overdue: Mapped[int] = mapped_column(Integer, default=0)
    transcript_hash: Mapped[Optional[str]] = mapped_column(String(64), default=None)

    borrower: Mapped[Borrower] = relationship(back_populates="calls")
    turns: Mapped[list["Turn"]] = relationship(back_populates="call", cascade="all, delete-orphan")


class Turn(Base):
    """One side of one back-and-forth."""

    __tablename__ = "turns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id"))
    role: Mapped[str] = mapped_column(String(16))  # 'aria' | 'borrower'
    text: Mapped[str] = mapped_column(Text)
    intent: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    emotion_score: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    call: Mapped[Call] = relationship(back_populates="turns")


class PromiseToPay(Base):
    __tablename__ = "promises_to_pay"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id"))
    amount: Mapped[int] = mapped_column(Integer)
    promised_for: Mapped[Optional[str]] = mapped_column(String(64))  # human phrase or ISO date
    captured_at: Mapped[datetime] = mapped_column(server_default=func.now())
    confirmed_via: Mapped[str] = mapped_column(String(16), default="sms")


class AuditLog(Base):
    """Tamper-evident — each row stores SHA-256 of preceding hash + payload."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id"))
    event_type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64), default="")
    self_hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    @staticmethod
    def compute_hash(prev_hash: str, payload: dict) -> str:
        import json as _json
        material = (prev_hash + _json.dumps(payload, sort_keys=True)).encode()
        return hashlib.sha256(material).hexdigest()


# ─── Engine + session ────────────────────────────────────────────

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            get_settings().database_url,
            echo=False,
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def init_db() -> None:
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)