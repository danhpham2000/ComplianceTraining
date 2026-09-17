from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


CONFIG_PATH = Path(__file__).resolve()


def _discover_root_dir() -> Path:
    candidates = [Path.cwd(), *CONFIG_PATH.parents]
    for marker in ["package.json", "apps/web/public"]:
        for candidate in candidates:
            if (candidate / marker).exists():
                return candidate
    for candidate in candidates:
        if (candidate / "pyproject.toml").exists():
            return candidate
    return Path.cwd()


ROOT_DIR = _discover_root_dir()


class Settings(BaseSettings):
    app_name: str = "Compliance Training API"
    api_v1_prefix: str = "/api/v1"
    web_app_url: str = "http://localhost:3000"
    database_url: str
    openai_api_key: str | None = None
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "sage"
    openai_video_model: str = "sora-2"
    openai_video_poll_interval_ms: int = 2000
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openrouter/free"
    firecrawl_api_key: str | None = None
    resend_api_key: str | None = None
    resend_from_email: str = "NextPhase <onboarding@resend.dev>"
    resend_reply_to: str | None = None
    openai_model: str = "gpt-5.4"
    app_env: str = "development"
    allowed_email_domain: str = "nextphase.ai"
    bootstrap_admin_email: str = "danhp@nextphase.ai"
    session_duration_days: int = 7
    verification_code_minutes: int = 15
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    model_config = SettingsConfigDict(extra="ignore")

    @property
    def email_delivery_enabled(self) -> bool:
        return bool(self.resend_api_key)


@lru_cache
def get_settings() -> Settings:
    candidates = [Path.cwd() / ".env", *(parent / ".env" for parent in CONFIG_PATH.parents)]
    existing = list(dict.fromkeys(path for path in candidates if path.exists()))
    return Settings(_env_file=existing or None)
