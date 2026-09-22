"""
Central configuration loader.

All configuration comes from environment variables (see .env.example).
This module loads and validates them ONCE at import/startup time and fails
fast with a clear message if something required is missing — no module
should read os.environ directly anywhere else in the app.

Never log the values of secret fields (tokens, API keys, client secrets).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

SECRET_FIELDS = {
    "telegram_bot_token",
    "openai_api_key",
    "gemini_api_key",
    "groq_api_key",
}


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill it in."
        )
    return value


def _optional(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    # Telegram
    telegram_bot_token: str
    telegram_owner_id: int

    # Gmail
    gmail_client_secret_path: Path
    gmail_token_path: Path
    gmail_state_path: Path
    gmail_poll_interval_seconds: int
    gmail_client_secret_json: str
    gmail_token_json: str

    # AI provider
    ai_provider: str
    ai_model: str
    openai_api_key: str
    gemini_api_key: str
    groq_api_key: str
    local_ai_base_url: str

    # Storage (Phase 1 uses SQLite; Phase 2 uses Postgres when DATABASE_URL is set)
    sqlite_path: Path

    # Phase 2: Postgres + pgvector
    database_url: str        # empty string = Phase 1 (SQLite) mode
    retention_days: int      # 0 = no retention sweep
    embedding_provider: str  # "openai" | "gemini"
    embedding_model: str

    # Phase 4: Proactive Intelligence
    digest_hour_utc: int
    deadline_reminder_window_hours: int
    followup_detection_days: int

    # Misc
    log_level: str

    def uses_database(self) -> bool:
        """True when DATABASE_URL is set — Phase 2+ Postgres path is active."""
        return bool(self.database_url)

    def __repr__(self) -> str:  # never leak secrets in logs/tracebacks
        safe = {
            k: ("***" if k in SECRET_FIELDS and v else v)
            for k, v in self.__dict__.items()
        }
        return f"Settings({safe})"


def load_settings() -> Settings:
    ai_provider = _optional("AI_PROVIDER", "gemini").lower()
    valid_providers = {"openai", "gemini", "groq", "local"}
    if ai_provider not in valid_providers:
        raise ConfigError(
            f"AI_PROVIDER must be one of {sorted(valid_providers)}, got {ai_provider!r}"
        )

    database_url = _optional("DATABASE_URL")
    embedding_provider = _optional("EMBEDDING_PROVIDER", "").lower()

    # When a database is configured, validate embedding_provider
    if database_url:
        valid_embedding_providers = {"openai", "gemini"}
        if not embedding_provider:
            # Default to the AI provider if it supports embeddings, else openai
            embedding_provider = ai_provider if ai_provider in valid_embedding_providers else "openai"
        if embedding_provider not in valid_embedding_providers:
            raise ConfigError(
                f"EMBEDDING_PROVIDER must be one of {sorted(valid_embedding_providers)} "
                f"(groq/local don't support embeddings), got {embedding_provider!r}"
            )
        # Ensure the embedding provider has an API key
        embedding_key = {
            "openai": _optional("OPENAI_API_KEY"),
            "gemini": _optional("GEMINI_API_KEY"),
        }[embedding_provider]
        if not embedding_key:
            raise ConfigError(
                f"EMBEDDING_PROVIDER={embedding_provider} but the matching API key is empty."
            )

    settings = Settings(
        telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
        telegram_owner_id=int(_require("TELEGRAM_OWNER_ID")),
        gmail_client_secret_path=Path(_optional("GMAIL_CLIENT_SECRET_PATH", "./data/client_secret.json")),
        gmail_token_path=Path(_optional("GMAIL_TOKEN_PATH", "./data/gmail_token.json")),
        gmail_state_path=Path(_optional("GMAIL_STATE_PATH", "./data/gmail_state.json")),
        gmail_poll_interval_seconds=int(_optional("GMAIL_POLL_INTERVAL_SECONDS", "60")),
        gmail_client_secret_json=_optional("GMAIL_CLIENT_SECRET_JSON"),
        gmail_token_json=_optional("GMAIL_TOKEN_JSON"),
        ai_provider=ai_provider,
        ai_model=_optional("AI_MODEL", "gemini-1.5-flash"),
        openai_api_key=_optional("OPENAI_API_KEY"),
        gemini_api_key=_optional("GEMINI_API_KEY"),
        groq_api_key=_optional("GROQ_API_KEY"),
        local_ai_base_url=_optional("LOCAL_AI_BASE_URL", "http://localhost:11434/v1"),
        sqlite_path=Path(_optional("SQLITE_PATH", "./data/email_agent.db")),
        database_url=database_url,
        retention_days=int(_optional("RETENTION_DAYS", "0")),
        embedding_provider=embedding_provider,
        embedding_model=_optional("EMBEDDING_MODEL", "text-embedding-3-small"),
        digest_hour_utc=int(_optional("DIGEST_HOUR_UTC", "8")),
        deadline_reminder_window_hours=int(_optional("DEADLINE_REMINDER_WINDOW_HOURS", "24")),
        followup_detection_days=int(_optional("FOLLOWUP_DETECTION_DAYS", "5")),
        log_level=_optional("LOG_LEVEL", "INFO").upper(),
    )

    key_by_provider = {
        "openai": settings.openai_api_key,
        "gemini": settings.gemini_api_key,
        "groq": settings.groq_api_key,
        "local": "not-needed",
    }
    if not key_by_provider[settings.ai_provider]:
        raise ConfigError(
            f"AI_PROVIDER={settings.ai_provider} but the matching API key env var is empty."
        )

    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    settings.gmail_token_path.parent.mkdir(parents=True, exist_ok=True)

    # If JSON is provided via environment variables (e.g. on Render/Railway), write it to disk
    import base64
    if settings.gmail_client_secret_json:
        try:
            # Try parsing as base64 first, fallback to raw string
            decoded = base64.b64decode(settings.gmail_client_secret_json).decode("utf-8")
        except Exception:
            decoded = settings.gmail_client_secret_json
        settings.gmail_client_secret_path.write_text(decoded, encoding="utf-8")

    if settings.gmail_token_json:
        try:
            decoded = base64.b64decode(settings.gmail_token_json).decode("utf-8")
        except Exception:
            decoded = settings.gmail_token_json
        settings.gmail_token_path.write_text(decoded, encoding="utf-8")

    return settings


settings = load_settings()
