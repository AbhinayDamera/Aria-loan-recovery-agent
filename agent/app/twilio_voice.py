"""Twilio Media Streams handler.

Now accepts borrower_id from the query string (passed by main.py via TwiML),
and loads the actual borrower record from the database before starting
the conversation. Falls back to DEMO_BORROWER only if borrower_id missing
or DB lookup fails.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger

from app.agent_brain import AgentBrain
from app.borrower_repo import get_borrower
from app.conversation import DEMO_BORROWER, BorrowerContext
from app.emotion import EmotionAnalyzer
from app.events import Event, EventType, event_bus
from app.voice_pipeline import (
    DeepgramStream,
    ElevenLabsTTS,
    decode_twilio_media_frame,
    encode_twilio_media_frame,
)


# ─── Pending borrower stash ──────────────────────────────────────
# Maps Twilio call_sid → borrower_id. Set by /api/borrowers/{id}/call
# in case the query parameter doesn't survive the Twilio webhook chain.
_PENDING_BORROWERS: dict[str, str] = {}

# Maps Twilio call_sid → synthetic borrower dict. Set by /api/quick-call.
# These borrowers are NOT in the DB — they live only in memory for one call.
_PENDING_SYNTHETIC: dict[str, dict] = {}


def set_pending_borrower_id(call_sid: str, borrower_id: str) -> None:
    """Stash a borrower_id keyed by Twilio call_sid."""
    _PENDING_BORROWERS[call_sid] = borrower_id
    # Cleanup old entries (keep last 100)
    if len(_PENDING_BORROWERS) > 100:
        # Remove oldest half
        keys = list(_PENDING_BORROWERS.keys())[:50]
        for k in keys:
            _PENDING_BORROWERS.pop(k, None)


def pop_pending_borrower_id(call_sid: str) -> Optional[str]:
    """Retrieve and remove a stashed borrower_id."""
    return _PENDING_BORROWERS.pop(call_sid, None)


def set_pending_synthetic_borrower(call_sid: str, borrower: dict) -> None:
    """Stash a synthetic borrower dict (from quick-call) by Twilio call_sid."""
    _PENDING_SYNTHETIC[call_sid] = borrower
    if len(_PENDING_SYNTHETIC) > 50:
        keys = list(_PENDING_SYNTHETIC.keys())[:25]
        for k in keys:
            _PENDING_SYNTHETIC.pop(k, None)


def pop_pending_synthetic_borrower(call_sid: str) -> Optional[dict]:
    """Retrieve and remove a stashed synthetic borrower."""
    return _PENDING_SYNTHETIC.pop(call_sid, None)


# Pacing constants
FRAME_BYTES = 160
FRAMES_PER_BURST = 5
BURST_INTERVAL_S = 0.100


def _borrower_dict_to_context(b: dict) -> BorrowerContext:
    """Convert a database row to a BorrowerContext for the brain."""
    return BorrowerContext(
        borrower_id=b["id"],
        borrower_name=b["name"],
        lender_name="Aria Bank",
        overdue_amount=b["overdue_amount"],
        days_overdue=b["days_overdue"],
        emi_amount=b["emi_amount"],
        tenure_remaining_months=b["tenure_remaining_months"],
        preferred_language=b.get("language_pref", "en-in"),
        history_notes=[],  # could load from past calls if we want
    )


class TwilioCallSession:
    """One instance per active phone call."""

    def __init__(
        self,
        websocket: WebSocket,
        borrower_id: Optional[str] = None,
    ) -> None:
        self.ws = websocket
        self.stream_sid: Optional[str] = None
        self.call_sid: Optional[str] = None
        self.call_id: str = ""
        self.borrower_id: Optional[str] = borrower_id

        self.brain: Optional[AgentBrain] = None
        self.stt: Optional[DeepgramStream] = None
        self.tts: ElevenLabsTTS = ElevenLabsTTS()
        self.emotion = EmotionAnalyzer()

        self._closed = False
        self._media_count = 0
        self._tts_send_lock = asyncio.Lock()

    async def run(self) -> None:
        try:
            async for raw in self.ws.iter_text():
                try:
                    frame = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                kind = frame.get("event")

                if kind == "connected":
                    logger.info("Twilio stream connected")

                elif kind == "start":
                    await self._on_start(frame)

                elif kind == "media":
                    await self._on_media(frame)

                elif kind == "stop":
                    logger.info(f"[{self.call_id}] Twilio stream stopped")
                    break

                elif kind == "mark":
                    pass

        except WebSocketDisconnect:
            logger.info(f"[{self.call_id}] Twilio WS disconnected")
        except Exception as e:
            logger.exception(f"[{self.call_id}] Twilio session error: {e}")
        finally:
            await self._cleanup()

    async def _on_start(self, frame: dict) -> None:
        start = frame.get("start", {})
        self.stream_sid = start.get("streamSid")
        self.call_sid = start.get("callSid")
        self.call_id = self.call_sid or self.stream_sid or "unknown-call"

        logger.info(f"[{self.call_id}] call started · streamSid={self.stream_sid}")

        # First check: was this a quick-call with a synthetic borrower?
        synthetic = None
        if self.call_sid:
            synthetic = pop_pending_synthetic_borrower(self.call_sid)

        # Resolve borrower_id from multiple sources (only if no synthetic)
        if not synthetic and not self.borrower_id and self.call_sid:
            self.borrower_id = pop_pending_borrower_id(self.call_sid)
            if self.borrower_id:
                logger.info(f"[{self.call_id}] Recovered borrower_id={self.borrower_id} from stash")

        # Load borrower context
        borrower_ctx: BorrowerContext
        if synthetic:
            borrower_ctx = _borrower_dict_to_context(synthetic)
            logger.info(
                f"[{self.call_id}] Using synthetic borrower: {borrower_ctx.borrower_name} "
                f"(quick-call, not in DB)"
            )
        elif self.borrower_id:
            try:
                row = await get_borrower(self.borrower_id)
                if row is not None:
                    borrower_ctx = _borrower_dict_to_context(row)
                    logger.info(
                        f"[{self.call_id}] Loaded borrower: {borrower_ctx.borrower_name} "
                        f"(id={self.borrower_id})"
                    )
                else:
                    logger.warning(
                        f"[{self.call_id}] borrower_id={self.borrower_id} not found, falling back to demo"
                    )
                    borrower_ctx = DEMO_BORROWER
            except Exception as e:
                logger.error(f"[{self.call_id}] DB lookup failed: {e}, falling back to demo")
                borrower_ctx = DEMO_BORROWER
        else:
            logger.info(f"[{self.call_id}] No borrower_id, using DEMO_BORROWER")
            borrower_ctx = DEMO_BORROWER

        # Spin up the brain with the right borrower
        self.brain = AgentBrain(call_id=self.call_id, borrower=borrower_ctx)

        self.stt = DeepgramStream(on_final=self._on_user_utterance)
        try:
            await self.stt.start()
        except Exception as e:
            logger.error(f"[{self.call_id}] Failed to start Deepgram: {e}")
            return

        # Aria speaks first (non-blocking task)
        opening = await self.brain.opening_line()
        asyncio.create_task(self._speak(opening))

    async def _on_media(self, frame: dict) -> None:
        if self._closed:
            return

        mulaw = decode_twilio_media_frame(frame)
        if not mulaw:
            return

        if self.stt:
            try:
                await self.stt.send_audio(mulaw)
            except Exception as e:
                logger.warning(f"STT forward failed: {e}")

        self._media_count += 1
        if self._media_count % 250 == 0:
            logger.debug(f"[{self.call_id}] received {self._media_count} media frames")

    async def _on_user_utterance(self, text: str) -> None:
        if not self.brain or self._closed:
            return

        if len(text.strip()) < 2:
            return

        logger.info(f"[{self.call_id}] borrower: {text}")

        try:
            reply = await self.brain.respond(text)
        except Exception as e:
            logger.error(f"[{self.call_id}] brain.respond error: {e}")
            return

        if reply:
            logger.info(f"[{self.call_id}] aria: {reply}")
            asyncio.create_task(self._speak(reply))

    async def _speak(self, text: str) -> None:
        if self._closed or not self.stream_sid:
            return

        async with self._tts_send_lock:
            try:
                audio_buffer = bytearray()
                async for chunk in self.tts.synthesize_stream(text):
                    if self._closed:
                        return
                    if chunk:
                        audio_buffer.extend(chunk)

                if not audio_buffer:
                    logger.warning(f"[{self.call_id}] TTS returned empty audio")
                    return

                logger.debug(
                    f"[{self.call_id}] TTS done · {len(audio_buffer)} bytes "
                    f"({len(audio_buffer) / 8000:.2f}s of audio)"
                )

                total_frames = len(audio_buffer) // FRAME_BYTES
                bursts_sent = 0
                next_burst_time = time.monotonic()

                for i in range(0, len(audio_buffer), FRAME_BYTES * FRAMES_PER_BURST):
                    if self._closed:
                        break

                    burst_data = bytes(audio_buffer[i : i + FRAME_BYTES * FRAMES_PER_BURST])
                    for j in range(0, len(burst_data), FRAME_BYTES):
                        slice_ = burst_data[j : j + FRAME_BYTES]
                        if len(slice_) < FRAME_BYTES:
                            slice_ = slice_ + (b"\xff" * (FRAME_BYTES - len(slice_)))
                        frame = encode_twilio_media_frame(slice_, self.stream_sid)
                        try:
                            await self.ws.send_text(json.dumps(frame))
                        except Exception as e:
                            logger.warning(f"WS send failed: {e}")
                            return

                    bursts_sent += 1
                    next_burst_time += BURST_INTERVAL_S
                    sleep_for = next_burst_time - time.monotonic()
                    if sleep_for > 0:
                        await asyncio.sleep(sleep_for)

                logger.debug(
                    f"[{self.call_id}] sent {bursts_sent} bursts ({total_frames} frames total)"
                )
            except Exception as e:
                logger.error(f"[{self.call_id}] TTS speak error: {e}")

    async def _cleanup(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self.stt:
                await self.stt.close()
        except Exception:
            pass
        try:
            await self.tts.aclose()
        except Exception:
            pass
        if self.brain:
            await self.brain.close()
        logger.info(f"[{self.call_id}] session cleaned up")