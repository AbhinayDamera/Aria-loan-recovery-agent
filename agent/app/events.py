"""Event bus — Pipecat agent publishes, dashboard WebSocket subscribes.

Events flow as JSON on Redis pub/sub channels:
  - aria:call:{call_id}    every event for that one call
  - aria:calls               global stream (call started, ended, etc.)
"""

from __future__ import annotations

import json
import time
from enum import Enum
from typing import Any, AsyncGenerator

import redis.asyncio as aioredis
from loguru import logger
from pydantic import BaseModel, Field

from app.config import get_settings


class EventType(str, Enum):
    CALL_STARTED = "call_started"
    CALL_ENDED = "call_ended"
    TRANSCRIPT = "transcript"
    INTENT = "intent"
    EMOTION = "emotion"
    PTP_CAPTURED = "ptp_captured"
    ESCALATION = "escalation"
    AGENT_STATE = "agent_state"


class Event(BaseModel):
    type: EventType
    call_id: str
    timestamp: float = Field(default_factory=time.time)
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_json(self) -> str:
        return self.model_dump_json()


class EventBus:
    def __init__(self) -> None:
        self._url = get_settings().redis_url
        self._client: aioredis.Redis | None = None

    async def connect(self) -> None:
        if self._client is None:
            self._client = aioredis.from_url(self._url, decode_responses=True)
            await self._client.ping()
            logger.info("Redis event bus connected")

    async def publish(self, event: Event) -> None:
        if self._client is None:
            await self.connect()
        assert self._client is not None
        payload = event.to_json()
        await self._client.publish(f"aria:call:{event.call_id}", payload)
        await self._client.publish("aria:calls", payload)

    async def subscribe(self, call_id: str | None = None) -> AsyncGenerator[Event, None]:
        if self._client is None:
            await self.connect()
        assert self._client is not None
        channel = f"aria:call:{call_id}" if call_id else "aria:calls"
        pubsub = self._client.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                    yield Event.model_validate(data)
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Bad event payload: {e}")
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# Module-level singleton — one bus per process is enough.
event_bus = EventBus()