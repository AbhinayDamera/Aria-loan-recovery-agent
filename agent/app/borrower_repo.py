"""Borrower repository — async access to Supabase aria_* tables.

Uses raw SQL via asyncpg for simplicity and to avoid coupling with the
existing SQLAlchemy models (which use a different schema).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

import asyncpg
from loguru import logger

from app.config import get_settings


# ─── Connection pool ──────────────────────────────────────────────

_pool: asyncpg.Pool | None = None


def _supabase_dsn() -> str:
    """Convert the SQLAlchemy URL we already have to a plain asyncpg DSN."""
    url = get_settings().database_url
    # Our config stores 'postgresql+asyncpg://...'; asyncpg wants 'postgresql://...'
    return url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql+psycopg://", "postgresql://"
    )


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            _supabase_dsn(),
            min_size=1,
            max_size=5,
            command_timeout=10.0,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


# ─── Helpers ──────────────────────────────────────────────────────


def _row_to_dict(row: asyncpg.Record | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {k: _serialize_value(v) for k, v in dict(row).items()}


def _serialize_value(v: Any) -> Any:
    """Convert datetime/date to ISO strings for JSON safety."""
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def _rows_to_list(rows: list[asyncpg.Record]) -> list[dict[str, Any]]:
    return [_row_to_dict(r) for r in rows if r is not None]  # type: ignore


# ─── Borrowers ────────────────────────────────────────────────────


async def list_borrowers(
    *,
    status: Optional[str] = None,
    risk_tier: Optional[str] = None,
    intent: Optional[str] = None,
    sort: str = "days_overdue",
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return borrowers with optional filters."""
    pool = await get_pool()

    where_clauses: list[str] = ["status != 'dnc'"]  # never show DNC borrowers
    params: list[Any] = []

    if status:
        params.append(status)
        where_clauses.append(f"status = ${len(params)}")

    if risk_tier:
        params.append(risk_tier)
        where_clauses.append(f"risk_tier = ${len(params)}")

    if intent:
        params.append(intent)
        where_clauses.append(f"primary_intent = ${len(params)}")

    where_sql = " AND ".join(where_clauses)

    # Whitelist sort columns to prevent SQL injection
    sort_col = {
        "days_overdue": "days_overdue DESC",
        "overdue_amount": "overdue_amount DESC",
        "risk_score": "risk_score DESC",
        "last_contacted": "last_contacted_at DESC NULLS LAST",
        "name": "name ASC",
    }.get(sort, "days_overdue DESC")

    params.append(limit)
    sql = f"""
        SELECT id, name, phone, language_pref, location,
               loan_principal, emi_amount, tenure_months, tenure_remaining_months,
               days_overdue, overdue_amount, total_outstanding,
               risk_score, risk_tier, status, primary_intent,
               last_contacted_at, created_at
        FROM aria_borrowers
        WHERE {where_sql}
        ORDER BY {sort_col}
        LIMIT ${len(params)}
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
    return _rows_to_list(rows)


async def get_borrower(borrower_id: str) -> Optional[dict[str, Any]]:
    """Get full borrower record by ID."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM aria_borrowers WHERE id = $1",
            borrower_id,
        )
    return _row_to_dict(row)


# ─── Calls ────────────────────────────────────────────────────────


async def get_borrower_calls(
    borrower_id: str, limit: int = 20
) -> list[dict[str, Any]]:
    """Return past calls for a borrower with summaries joined in."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                c.id, c.started_at, c.ended_at, c.duration_seconds,
                c.outcome, c.intent_detected, c.distress_peak,
                c.personality_modes_used, c.escalated,
                c.ptp_amount, c.ptp_date, c.ptp_kept,
                s.summary, s.promises_made, s.concerns_raised
            FROM aria_calls c
            LEFT JOIN aria_call_summaries s ON s.call_id = c.id
            WHERE c.borrower_id = $1
            ORDER BY c.started_at DESC
            LIMIT $2
            """,
            borrower_id,
            limit,
        )
    return _rows_to_list(rows)


# ─── Payments ─────────────────────────────────────────────────────


async def get_borrower_payments(
    borrower_id: str, limit: int = 12
) -> list[dict[str, Any]]:
    """Return payment timeline for a borrower (newest first)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, due_date, paid_date, amount, status
            FROM aria_payments
            WHERE borrower_id = $1
            ORDER BY due_date DESC
            LIMIT $2
            """,
            borrower_id,
            limit,
        )
    return _rows_to_list(rows)


# ─── Stats ────────────────────────────────────────────────────────


async def get_today_stats() -> dict[str, Any]:
    """Aggregate metrics for the dashboard header."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Calls today
        calls_today_row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS calls,
                COUNT(*) FILTER (WHERE outcome = 'ptp_captured') AS ptps,
                COUNT(*) FILTER (WHERE escalated = TRUE) AS escalations,
                COALESCE(AVG(duration_seconds), 0)::INT AS avg_duration
            FROM aria_calls
            WHERE started_at::date = CURRENT_DATE
            """
        )

        # Total queue
        queue_row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE risk_tier = 'critical') AS critical,
                COUNT(*) FILTER (WHERE risk_tier = 'high') AS high,
                COUNT(*) FILTER (WHERE primary_intent = 'hardship') AS hardship,
                COALESCE(SUM(overdue_amount), 0)::BIGINT AS total_overdue
            FROM aria_borrowers
            WHERE status NOT IN ('dnc', 'resolved')
            """
        )

        # PTP rate (last 30 days)
        ptp_rate_row = await conn.fetchrow(
            """
            SELECT
                COALESCE(
                    100.0 * COUNT(*) FILTER (WHERE outcome = 'ptp_captured')
                    / NULLIF(COUNT(*), 0),
                    0
                )::INT AS ptp_rate
            FROM aria_calls
            WHERE started_at >= NOW() - INTERVAL '30 days'
              AND outcome IS NOT NULL
            """
        )

    return {
        "calls_today": calls_today_row["calls"],
        "ptps_today": calls_today_row["ptps"],
        "escalations_today": calls_today_row["escalations"],
        "avg_duration_seconds": calls_today_row["avg_duration"],
        "queue_total": queue_row["total"],
        "queue_critical": queue_row["critical"],
        "queue_high": queue_row["high"],
        "queue_hardship": queue_row["hardship"],
        "total_overdue_amount": queue_row["total_overdue"],
        "ptp_rate_30d": ptp_rate_row["ptp_rate"],
        "compliance_violations": 0,  # always 0 — talking point
    }


# ─── Updates ──────────────────────────────────────────────────────


async def mark_borrower_contacted(borrower_id: str) -> None:
    """Update last_contacted_at after a call is triggered."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE aria_borrowers
            SET last_contacted_at = NOW(),
                status = CASE WHEN status = 'pending' THEN 'contacted' ELSE status END,
                updated_at = NOW()
            WHERE id = $1
            """,
            borrower_id,
        )