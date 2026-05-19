"""FastAPI entry point with operations console API.

Fixed: borrower_id is now passed through the Twilio webhook chain so that
when a call connects, Aria knows WHICH borrower it's actually talking to.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from loguru import logger

from app.borrower_repo import (
    close_pool as close_borrower_pool,
    get_borrower,
    get_borrower_calls,
    get_borrower_payments,
    get_today_stats,
    list_borrowers,
    mark_borrower_contacted,
)
from app.config import get_settings
from app.db import init_db
from app.events import event_bus
from app.twilio_voice import TwilioCallSession, set_pending_borrower_id


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_settings()
    logger.info(f"Aria agent starting · demo_mode={cfg.demo_mode}")
    try:
        await init_db()
    except Exception as e:
        logger.warning(f"DB init skipped: {e}")
    try:
        await event_bus.connect()
    except Exception as e:
        logger.warning(f"Redis connect failed: {e}")
    yield
    try:
        await event_bus.aclose()
    except Exception:
        pass
    try:
        await close_borrower_pool()
    except Exception:
        pass
    logger.info("Aria agent stopped")


app = FastAPI(title="Aria — AI loan recovery", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health ──────────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "demo_mode": get_settings().demo_mode}


# ─── Twilio Answer URL ───────────────────────────────────────────


@app.api_route("/twilio/answer", methods=["GET", "POST"])
async def twilio_answer(
    request: Request,
    borrower_id: Optional[str] = Query(default=None),
) -> PlainTextResponse:
    """Twilio webhook. We accept ?borrower_id=... and stash it so the
    /twilio/stream WebSocket can pick up the right borrower context."""
    cfg = get_settings()
    base = cfg.public_base_url.replace("https://", "wss://").replace("http://", "ws://")

    # Pass borrower_id through to the WebSocket via the stream URL
    if borrower_id:
        stream_url = f"{base}/twilio/stream?borrower_id={borrower_id}"
        logger.info(f"Twilio answer · borrower_id={borrower_id}")
    else:
        stream_url = f"{base}/twilio/stream"
        logger.info("Twilio answer · no borrower_id (using DEMO_BORROWER)")

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{stream_url}" />
  </Connect>
</Response>"""
    return PlainTextResponse(twiml, media_type="application/xml")


# ─── Twilio Media Streams WebSocket ──────────────────────────────


@app.websocket("/twilio/stream")
async def twilio_stream(
    ws: WebSocket,
    borrower_id: Optional[str] = Query(default=None),
) -> None:
    """Bidirectional audio bridge. borrower_id (from query) tells us which
    borrower context to load."""
    await ws.accept()
    session = TwilioCallSession(ws, borrower_id=borrower_id)
    await session.run()


# ─── Operations Console API ──────────────────────────────────────


@app.get("/api/borrowers")
async def api_list_borrowers(
    status: Optional[str] = Query(default=None),
    risk_tier: Optional[str] = Query(default=None),
    intent: Optional[str] = Query(default=None),
    sort: str = Query(default="days_overdue"),
    limit: int = Query(default=100, le=500),
) -> JSONResponse:
    try:
        rows = await list_borrowers(
            status=status,
            risk_tier=risk_tier,
            intent=intent,
            sort=sort,
            limit=limit,
        )
        return JSONResponse({"borrowers": rows, "count": len(rows)})
    except Exception as e:
        logger.exception("list_borrowers failed")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/borrowers/{borrower_id}")
async def api_get_borrower(borrower_id: str) -> JSONResponse:
    try:
        row = await get_borrower(borrower_id)
        if row is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(row)
    except Exception as e:
        logger.exception("get_borrower failed")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/borrowers/{borrower_id}/calls")
async def api_get_borrower_calls(borrower_id: str) -> JSONResponse:
    try:
        calls = await get_borrower_calls(borrower_id)
        return JSONResponse({"calls": calls, "count": len(calls)})
    except Exception as e:
        logger.exception("get_borrower_calls failed")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/borrowers/{borrower_id}/payments")
async def api_get_borrower_payments(borrower_id: str) -> JSONResponse:
    try:
        payments = await get_borrower_payments(borrower_id)
        return JSONResponse({"payments": payments, "count": len(payments)})
    except Exception as e:
        logger.exception("get_borrower_payments failed")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/borrowers/{borrower_id}/call")
async def api_call_borrower(borrower_id: str) -> JSONResponse:
    """Trigger an outbound call to a specific borrower.

    Critical: we pass borrower_id through Twilio's webhook URL so that
    when the call connects, the agent loads the RIGHT borrower context.
    """
    cfg = get_settings()

    borrower = await get_borrower(borrower_id)
    if borrower is None:
        return JSONResponse({"error": "borrower not found"}, status_code=404)

    if borrower["status"] == "dnc":
        return JSONResponse(
            {"error": "borrower is on DNC list"}, status_code=403
        )

    to_number = cfg.verified_phone_number or borrower["phone"]

    if not cfg.twilio_account_sid or not cfg.twilio_auth_token:
        return JSONResponse(
            {"error": "Twilio credentials missing"}, status_code=500
        )

    # CRITICAL: pass borrower_id as query param so /twilio/answer knows
    # which borrower this call is for
    answer_url = f"{cfg.public_base_url}/twilio/answer?borrower_id={borrower_id}"

    try:
        from twilio.rest import Client

        client = Client(cfg.twilio_account_sid, cfg.twilio_auth_token)
        call = client.calls.create(
            to=to_number,
            from_=cfg.twilio_phone_number,
            url=answer_url,
            method="POST",
        )

        # Stash the mapping so the WebSocket session can pick it up
        # (in case the URL param doesn't come through)
        set_pending_borrower_id(call.sid, borrower_id)

        await mark_borrower_contacted(borrower_id)

        logger.info(
            f"Outbound call to {borrower['name']} (id={borrower_id}) queued · sid={call.sid}"
        )
        return JSONResponse(
            {
                "call_sid": call.sid,
                "to": to_number,
                "borrower_id": borrower_id,
                "borrower_name": borrower["name"],
            }
        )
    except Exception as e:
        logger.exception("api_call_borrower failed")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/stats")
async def api_get_stats() -> JSONResponse:
    try:
        stats = await get_today_stats()
        return JSONResponse(stats)
    except Exception as e:
        logger.exception("get_today_stats failed")
        return JSONResponse({"error": str(e)}, status_code=500)


# ─── Quick-call (inline borrower, no DB save) ────────────────────


@app.post("/api/quick-call")
async def api_quick_call(request: Request) -> JSONResponse:
    """Trigger a call to a one-off borrower entered manually on the dashboard.

    Body JSON:
    {
      "name": "Asha Kumari",
      "phone": "+919876543210",
      "days_overdue": 12,
      "overdue_amount": 5000,
      "emi_amount": 5000,           // optional, defaults to overdue_amount
      "language_pref": "en-in",      // optional, defaults to en-in
      "loan_principal": 100000,      // optional
      "tenure_remaining_months": 18  // optional
    }

    The borrower data is held in memory keyed by Twilio call_sid and is
    NOT saved to the database.
    """
    cfg = get_settings()

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)

    # Required fields
    name = (body.get("name") or "").strip()
    phone = (body.get("phone") or "").strip()
    if not name or not phone:
        return JSONResponse(
            {"error": "name and phone are required"}, status_code=400
        )

    # Normalize phone: ensure +91 prefix
    if not phone.startswith("+"):
        phone = "+91" + phone.lstrip("0")

    # Optional fields with defaults
    try:
        days_overdue = int(body.get("days_overdue", 5))
        overdue_amount = int(body.get("overdue_amount", 4500))
        emi_amount = int(body.get("emi_amount", overdue_amount))
        loan_principal = int(body.get("loan_principal", emi_amount * 24))
        tenure_remaining = int(body.get("tenure_remaining_months", 18))
    except (TypeError, ValueError):
        return JSONResponse(
            {"error": "numeric fields must be integers"}, status_code=400
        )

    language_pref = body.get("language_pref") or "en-in"

    if not cfg.twilio_account_sid or not cfg.twilio_auth_token:
        return JSONResponse(
            {"error": "Twilio credentials missing"}, status_code=500
        )

    # Build a synthetic borrower context dict matching DB shape
    synthetic_borrower = {
        "id": f"QUICK-{int(asyncio.get_event_loop().time() * 1000)}",
        "name": name,
        "phone": phone,
        "language_pref": language_pref,
        "location": body.get("location") or "—",
        "loan_principal": loan_principal,
        "emi_amount": emi_amount,
        "tenure_months": 24,
        "tenure_remaining_months": tenure_remaining,
        "days_overdue": days_overdue,
        "overdue_amount": overdue_amount,
        "total_outstanding": loan_principal,
        "risk_score": 50,
        "risk_tier": "medium",
        "status": "pending",
        "primary_intent": None,
        "last_contacted_at": None,
    }

    # Use entered phone directly (assumes paid Twilio)
    answer_url = f"{cfg.public_base_url}/twilio/answer?quick_call=1"

    try:
        from twilio.rest import Client

        client = Client(cfg.twilio_account_sid, cfg.twilio_auth_token)
        call = client.calls.create(
            to=phone,
            from_=cfg.twilio_phone_number,
            url=answer_url,
            method="POST",
        )

        # Stash synthetic borrower for the WebSocket session
        from app.twilio_voice import set_pending_synthetic_borrower
        set_pending_synthetic_borrower(call.sid, synthetic_borrower)

        logger.info(
            f"Quick-call to {name} ({phone}) queued · sid={call.sid}"
        )
        return JSONResponse(
            {
                "call_sid": call.sid,
                "to": phone,
                "borrower_name": name,
            }
        )
    except Exception as e:
        logger.exception("quick-call failed")
        # Return Twilio error message clearly so user knows what to fix
        return JSONResponse(
            {"error": str(e), "hint": "If on Twilio trial, verify the number first"},
            status_code=500,
        )


# ─── Outbound call trigger (legacy — uses DEMO_BORROWER) ─────────


@app.post("/calls/start")
async def start_call(request: Request) -> JSONResponse:
    cfg = get_settings()
    try:
        body = await request.json()
    except Exception:
        body = {}

    to_number = body.get("to") or cfg.verified_phone_number
    if not to_number:
        return JSONResponse(
            {"error": "VERIFIED_PHONE_NUMBER not set"}, status_code=400
        )

    if not cfg.twilio_account_sid or not cfg.twilio_auth_token:
        return JSONResponse(
            {"error": "Twilio credentials missing"}, status_code=400
        )

    # Legacy script — defaults to BRW001 (Rahul) so it has real data
    answer_url = f"{cfg.public_base_url}/twilio/answer?borrower_id=BRW001"

    try:
        from twilio.rest import Client

        client = Client(cfg.twilio_account_sid, cfg.twilio_auth_token)
        call = client.calls.create(
            to=to_number,
            from_=cfg.twilio_phone_number,
            url=answer_url,
            method="POST",
        )
        set_pending_borrower_id(call.sid, "BRW001")
        logger.info(f"Outbound call queued · sid={call.sid} → {to_number}")
        return JSONResponse({"call_sid": call.sid, "to": to_number})
    except Exception as e:
        logger.exception("Outbound call failed")
        return JSONResponse({"error": str(e)}, status_code=500)


# ─── Dashboard WebSocket ─────────────────────────────────────────


@app.websocket("/ws/events")
async def dashboard_events(
    ws: WebSocket, call_id: str | None = Query(default=None)
) -> None:
    await ws.accept()
    logger.info(f"dashboard connected · call_id={call_id or '*'}")

    forward_task: asyncio.Task | None = None
    try:
        async def forward():
            async for event in event_bus.subscribe(call_id):
                await ws.send_text(event.to_json())

        forward_task = asyncio.create_task(forward())
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        logger.info("dashboard disconnected")
    finally:
        if forward_task and not forward_task.done():
            forward_task.cancel()


# ─── Demo helpers ────────────────────────────────────────────────


@app.post("/demo/inject-event")
async def inject_demo_event(payload: dict) -> dict:
    from app.events import Event, EventType

    event = Event(
        type=EventType(payload["type"]),
        call_id=payload["call_id"],
        payload=payload.get("payload", {}),
    )
    await event_bus.publish(event)
    return {"ok": True}