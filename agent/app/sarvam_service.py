"""Custom Pipecat services for Sarvam.ai (Hindi-English STT + TTS).

Pipecat ships native services for OpenAI/Deepgram/ElevenLabs but Sarvam
support varies by version. We ship our own thin clients here so the agent
works regardless. If Pipecat adds first-class Sarvam services upstream,
swap these out.

Sarvam endpoints used:
  POST  https://api.sarvam.ai/speech-to-text
  POST  https://api.sarvam.ai/text-to-speech

Verify endpoints + payload shapes against current docs:
  https://docs.sarvam.ai
"""

from __future__ import annotations

import asyncio
import base64
from typing import AsyncGenerator

import httpx
from loguru import logger

from app.config import get_settings


class SarvamSTT:
    """Send accumulated audio chunks to Sarvam, return transcribed text.

    For low-latency streaming you'd ideally use a websocket STT, but
    Sarvam's HTTP STT works for our hackathon scope. Buffer audio in
    ~1.5–2s chunks before flushing.
    """

    def __init__(self) -> None:
        cfg = get_settings()
        self._api_key = cfg.sarvam_api_key
        self._client = httpx.AsyncClient(
            base_url="https://api.sarvam.ai",
            headers={"api-subscription-key": self._api_key},
            timeout=10.0,
        )

    async def transcribe(self, wav_bytes: bytes, language_code: str = "hi-IN") -> str:
        """Transcribe a WAV (16kHz mono) buffer. Returns plain text."""
        files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
        data = {
            "language_code": language_code,
            "model": "saarika:v2",
            "with_timestamps": "false",
        }
        try:
            r = await self._client.post("/speech-to-text", files=files, data=data)
            r.raise_for_status()
            return (r.json().get("transcript") or "").strip()
        except httpx.HTTPError as e:
            logger.warning(f"Sarvam STT error: {e}")
            return ""

    async def aclose(self) -> None:
        await self._client.aclose()


class SarvamTTS:
    """Synthesize Hindi-English code-switched audio."""

    def __init__(self) -> None:
        cfg = get_settings()
        self._api_key = cfg.sarvam_api_key
        self._voice = cfg.sarvam_tts_voice
        self._language = cfg.sarvam_tts_language
        self._client = httpx.AsyncClient(
            base_url="https://api.sarvam.ai",
            headers={"api-subscription-key": self._api_key},
            timeout=15.0,
        )

    async def synthesize(self, text: str) -> bytes:
        """Synthesize text → WAV bytes (16kHz)."""
        if not text.strip():
            return b""

        payload = {
            "inputs": [text],
            "target_language_code": self._language,
            "speaker": self._voice,
            "model": "bulbul:v1",
            "speech_sample_rate": 16000,
            "enable_preprocessing": True,
        }
        try:
            r = await self._client.post("/text-to-speech", json=payload)
            r.raise_for_status()
            audio_b64 = r.json()["audios"][0]
            return base64.b64decode(audio_b64)
        except httpx.HTTPError as e:
            logger.warning(f"Sarvam TTS error: {e}")
            return b""

    async def stream(self, text: str) -> AsyncGenerator[bytes, None]:
        """Stream synthesis by splitting on punctuation for lower latency."""
        # Simple chunking — each clause goes to TTS independently so the
        # first audio frame returns ~300-500ms instead of waiting on the
        # whole sentence.
        clauses = self._split_clauses(text)
        for clause in clauses:
            audio = await self.synthesize(clause)
            if audio:
                yield audio
            await asyncio.sleep(0)  # cooperative yield

    @staticmethod
    def _split_clauses(text: str) -> list[str]:
        result: list[str] = []
        buf = ""
        for ch in text:
            buf += ch
            if ch in ".!?,।":
                if buf.strip():
                    result.append(buf.strip())
                buf = ""
        if buf.strip():
            result.append(buf.strip())
        return result

    async def aclose(self) -> None:
        await self._client.aclose()
