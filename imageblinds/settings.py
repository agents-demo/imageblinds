"""Model connection settings, read from the environment (.env).

Same contract as taketwo's ``integrations/agents/settings.py``: which provider,
credentials, base URL, model names and timeouts.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


class ConfigError(RuntimeError):
    """Raised when required backend configuration is missing or invalid."""


def _bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def model_provider() -> str:
    return os.getenv("MODEL_PROVIDER", "OpenAI")


def api_base() -> str:
    return os.getenv("API_BASE", "https://api.deepseek.com")


def api_key() -> str:
    return os.getenv("API_KEY", "")


def vision_model_name() -> str:
    return os.getenv("VISION_MODEL_NAME", "deepseek-v4-flash-vision-exp")


def vision_temperature() -> float:
    return float(os.getenv("VISION_TEMPERATURE", "0.2"))


def llm_retries() -> int:
    return int(os.getenv("LLM_RETRIES", "2"))


def llm_timeout() -> float:
    return float(os.getenv("LLM_TIMEOUT", "180"))


def verify_ssl() -> bool:
    return _bool("LLM_SSL_VERIFY", "false")


def validate() -> None:
    """Ensure the required backend environment variables are present.

    Only the API key is required; everything else has built-in defaults
    (the hosted deployment sets no other environment variables). ``MODEL_NAME``
    is taketwo's text-agent model and is not used by this app.
    """
    if not os.getenv("API_KEY"):
        raise ConfigError(
            "Missing required environment variable: API_KEY.\n"
            "Copy .env.example to .env and fill it in."
        )
