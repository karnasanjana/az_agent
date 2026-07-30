"""Application configuration using pydantic-settings."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    SEC-02: Settings are loaded from env vars only, never persisted.
    All sensitive values (fernet_key) must be provided via environment.
    """

    # Security (required - no defaults for secrets)
    fernet_key: str

    # Gemini Developer API (used by Schema Advisor)
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"

    # API server configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8443

    # TLS certificates (relative paths from backend/)
    ssl_keyfile: str = "certs/localhost+2-key.pem"
    ssl_certfile: str = "certs/localhost+2.pem"

    # Development mode (affects TLS validation)
    debug: bool = False

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, value):
        """Ignore unrelated host DEBUG values such as Windows' 'release'."""
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", "production", "prod", ""}:
                return False
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore unknown env vars
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Uses lru_cache to avoid re-reading .env file on every call.
    Cache is cleared on application restart.
    """
    return Settings()
