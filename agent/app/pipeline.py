"""Pipecat pipeline factory.

Builds the live conversation pipeline that runs for the duration of one
call. The full Pipecat wiring (Pipeline, FrameProcessor, transports) is
verbose — we keep this file focused on the orchestration shape and let
each service own its own logic.

The shape we want at runtime:

  PlivoTransport.input
       │  (raw PCM frames)
       ▼
  AudioBuffer ── tap ──▶  EmotionAnalyzer.push_audio
       │
       ▼
  SarvamSTT  ─────────▶  IntentExtractor + EmotionAnalyzer.push_semantic
       │
       ▼ (user message)
  ContextAggregator
       │
       ▼
  OpenAILLMService (GPT-4o)
       │
       ▼ (assistant message tokens)
  SarvamTTS  ─────────▶  PlivoTransport.output
       │
       ▼ (also publish events to Redis)
  EventEmitter

For initial scaffold we expose a `build_pipeline()` async factory. Track A
fills in the transport details against the current Pipecat version on
hour 8 of the sprint when telephony comes online.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from app.config import get_settings
from app.conversation import BorrowerContext
from app.emotion import EmotionAnalyzer
from app.events import Event, EventType, event_bus
from app.intent_extractor import IntentExtractor, IntentSignal, IntentType
from app.sarvam_service import SarvamSTT, SarvamTTS


@dataclass
class PipelineHandle:
    """Returned by build_pipeline — the runtime owner stops it on call end."""

    call_id: str
    stop_event: object  # asyncio.Event (typed loosely to avoid import cycle)


async def build_pipeline(
    call_id: str,
    borrower: BorrowerContext,
    plivo_websocket=None,
) -> PipelineHandle:
    """Wire up a Pipecat pipeline for a single call.

    During hour 0–8 (browser-mode dev) `plivo_websocket` is None and we
    expect to be driven by a local audio loop in `app.demo_browser`.

    During hour 8+ Track A fills in:
      - PlivoFrameSerializer for the inbound websocket
      - PlivoTransport input/output frames
      - The actual Pipecat Pipeline assembly
    """
    import asyncio

    cfg = get_settings()
    stop_event = asyncio.Event()

    # Shared singletons we hand to the per-call processors
    stt = SarvamSTT()
    tts = SarvamTTS()
    intent = IntentExtractor()
    emotion = EmotionAnalyzer()

    await event_bus.connect()
    await event_bus.publish(
        Event(
            type=EventType.CALL_STARTED,
            call_id=call_id,
            payload={
                "borrower_id": borrower.borrower_id,
                "borrower_name": borrower.borrower_name,
                "overdue_amount": borrower.overdue_amount,
                "days_overdue": borrower.days_overdue,
            },
        )
    )

    logger.info(
        f"[{call_id}] pipeline built · borrower={borrower.borrower_name} "
        f"language={cfg.sarvam_tts_language} model={cfg.openai_model}"
    )

    # NOTE: the actual Pipecat Pipeline(…) assembly lives in
    # `app.pipeline_runtime` (to be added on hour 8 against the current
    # Pipecat API). This file owns *what* we wire; the runtime owns *how*.
    return PipelineHandle(call_id=call_id, stop_event=stop_event)


async def handle_borrower_turn(
    call_id: str,
    utterance: str,
    intent: IntentExtractor,
    emotion: EmotionAnalyzer,
    recent_context: str = "",
) -> IntentSignal:
    """Called by the STT processor whenever a complete borrower turn arrives.

    Runs intent extraction + updates emotion semantic layer + publishes
    transcript and signal events to the dashboard.
    """
    signal = await intent.extract(utterance, recent_context)
    emotion.push_semantic(call_id, signal.distress_level)

    await event_bus.publish(
        Event(
            type=EventType.TRANSCRIPT,
            call_id=call_id,
            payload={"role": "borrower", "text": utterance},
        )
    )
    await event_bus.publish(
        Event(
            type=EventType.INTENT,
            call_id=call_id,
            payload=signal.model_dump(),
        )
    )
    await event_bus.publish(
        Event(
            type=EventType.EMOTION,
            call_id=call_id,
            payload={"score": emotion.score(call_id)},
        )
    )

    if signal.intent == IntentType.DISTRESS or emotion.score(call_id) >= get_settings().distress_threshold:
        await event_bus.publish(
            Event(
                type=EventType.ESCALATION,
                call_id=call_id,
                payload={
                    "reason": signal.intent.value,
                    "score": emotion.score(call_id),
                    "keywords": signal.keywords,
                },
            )
        )

    return signal
