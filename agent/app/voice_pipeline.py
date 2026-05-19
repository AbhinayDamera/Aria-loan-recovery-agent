"""Voice pipeline — Deepgram STT + OpenAI TTS, with mulaw conversion."""

from __future__ import annotations

import asyncio
import audioop
import base64
from typing import AsyncGenerator, Awaitable, Callable, Optional

import httpx
from deepgram import (
    DeepgramClient,
    LiveOptions,
    LiveTranscriptionEvents,
)
from loguru import logger

from app.config import get_settings


# ─── Deepgram (STT) ──────────────────────────────────────────────


class DeepgramStream:
    """Wraps Deepgram live transcription with a callback for finalized utterances."""

    def __init__(self, on_final: Callable[[str], Awaitable[None]]) -> None:
        self._on_final = on_final
        self._connection = None
        self._client = None
        self._closed = False

    async def start(self) -> None:
        cfg = get_settings()
        self._client = DeepgramClient(cfg.deepgram_api_key)
        self._connection = self._client.listen.asyncwebsocket.v("1")

        self._connection.on(LiveTranscriptionEvents.Transcript, self._handle_transcript)
        self._connection.on(LiveTranscriptionEvents.Error, self._handle_error)
        self._connection.on(LiveTranscriptionEvents.Open, self._handle_open)
        self._connection.on(LiveTranscriptionEvents.Close, self._handle_close)

        # English-only is more reliable. Hindi-English code-switch needs paid tier.
        options = LiveOptions(
            model="nova-2-phonecall",  # optimized for phone audio
            language="en",
            encoding="mulaw",
            sample_rate=8000,
            channels=1,
            interim_results=False,
            punctuate=True,
            endpointing=500,  # 500ms silence before considering utterance done
            smart_format=True,
        )
        ok = await self._connection.start(options)
        if not ok:
            logger.error("Deepgram connection failed to start")
            raise RuntimeError("Deepgram start failed")
        logger.info("Deepgram stream started")

    async def send_audio(self, mulaw_bytes: bytes) -> None:
        if self._closed or not self._connection:
            return
        try:
            await self._connection.send(mulaw_bytes)
        except Exception as e:
            logger.warning(f"Deepgram send error: {e}")

    async def _handle_open(self, *args, **kwargs) -> None:
        logger.info("Deepgram WS opened")

    async def _handle_close(self, *args, **kwargs) -> None:
        logger.info("Deepgram WS closed")

    async def _handle_transcript(self, *args, **kwargs) -> None:
        result = kwargs.get("result") or (args[1] if len(args) > 1 else None)
        if result is None:
            return
        try:
            sentence = result.channel.alternatives[0].transcript or ""
            is_final = result.is_final
        except Exception as e:
            logger.warning(f"Transcript parse error: {e}")
            return

        if sentence.strip():
            logger.debug(f"Transcript (final={is_final}): {sentence}")

        if is_final and sentence.strip():
            try:
                await self._on_final(sentence.strip())
            except Exception as e:
                logger.error(f"on_final handler error: {e}")

    async def _handle_error(self, *args, **kwargs) -> None:
        err = kwargs.get("error") or (args[1] if len(args) > 1 else None)
        logger.warning(f"Deepgram error: {err}")

    async def close(self) -> None:
        self._closed = True
        if self._connection:
            try:
                await self._connection.finish()
            except Exception:
                pass
        logger.info("Deepgram stream closed")


# ─── OpenAI TTS ──────────────────────────────────────────────────


class ElevenLabsTTS:
    """Class kept named ElevenLabsTTS for compatibility, but uses OpenAI TTS."""

    BASE_URL = "https://api.openai.com/v1/audio/speech"

    def __init__(self) -> None:
        cfg = get_settings()
        self._api_key = cfg.openai_api_key
        # OpenAI voices: alloy, echo, fable, onyx, nova, shimmer
        valid_voices = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}
        self._voice = cfg.elevenlabs_voice_id if cfg.elevenlabs_voice_id in valid_voices else "nova"
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))

    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        """Yield mulaw 8kHz audio chunks for the given text."""
        if not text.strip():
            return

        payload = {
            "model": "tts-1",
            "voice": self._voice,
            "input": text,
            "response_format": "pcm",  # 24kHz PCM 16-bit mono
            "speed": 1.0,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with self._client.stream(
                "POST", self.BASE_URL, json=payload, headers=headers
            ) as r:
                if r.status_code != 200:
                    body = await r.aread()
                    logger.error(f"OpenAI TTS failed: {r.status_code} {body[:200]!r}")
                    return

                # Single resample state for the whole stream — preserves continuity
                pcm_buffer = b""
                resample_state = None

                async for chunk in r.aiter_bytes(chunk_size=4800):
                    if not chunk:
                        continue
                    pcm_buffer += chunk

                    # Process complete blocks. 4800 bytes = 100ms @ 24kHz 16-bit.
                    block_size = 4800
                    while len(pcm_buffer) >= block_size:
                        block = pcm_buffer[:block_size]
                        pcm_buffer = pcm_buffer[block_size:]

                        # 24kHz PCM → 8kHz PCM (preserve resample state across calls)
                        downsampled, resample_state = audioop.ratecv(
                            block, 2, 1, 24000, 8000, resample_state
                        )
                        # 8kHz PCM → mulaw
                        mulaw = audioop.lin2ulaw(downsampled, 2)
                        yield mulaw

                # Drain leftover with the SAME resample state (not None!)
                if pcm_buffer:
                    downsampled, resample_state = audioop.ratecv(
                        pcm_buffer, 2, 1, 24000, 8000, resample_state
                    )
                    mulaw = audioop.lin2ulaw(downsampled, 2)
                    yield mulaw
        except Exception as e:
            logger.error(f"OpenAI TTS stream error: {e}")

    async def aclose(self) -> None:
        await self._client.aclose()


# ─── Twilio frame helpers ────────────────────────────────────────


def encode_twilio_media_frame(mulaw_chunk: bytes, stream_sid: str) -> dict:
    return {
        "event": "media",
        "streamSid": stream_sid,
        "media": {"payload": base64.b64encode(mulaw_chunk).decode("ascii")},
    }


def decode_twilio_media_frame(frame: dict) -> Optional[bytes]:
    """Pass the WHOLE Twilio frame (with 'event' and 'media' keys)."""
    try:
        b64 = frame["media"]["payload"]
        return base64.b64decode(b64)
    except (KeyError, TypeError):
        return None


def mulaw_rms(mulaw_bytes: bytes) -> float:
    try:
        pcm = audioop.ulaw2lin(mulaw_bytes, 2)
        rms = audioop.rms(pcm, 2)
        return min(1.0, rms / 8000.0)
    except Exception:
        return 0.0