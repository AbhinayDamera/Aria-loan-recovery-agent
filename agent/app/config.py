"""Typed configuration loaded from environment / .env.local."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env.local", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str
    openai_model: str = "gpt-4o-mini"

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    verified_phone_number: str = ""

    deepgram_api_key: str = ""

    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"

    public_base_url: str = "http://localhost:8000"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/aria"
    redis_url: str = "redis://localhost:6379/0"

    demo_mode: Literal["telephony", "browser"] = "telephony"
    distress_threshold: int = 80
    escalation_duration_seconds: int = 10

    app_port: int = 8000
    app_log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]