import logging
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

SECRET_KEY_MIN_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = Field(alias="SUPABASE_URL")
    supabase_anon_key: str = Field(alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str = Field(alias="SUPABASE_SERVICE_ROLE_KEY")
    database_url: str = Field(alias="DATABASE_URL")
    openrouter_api_key: str = Field(alias="OPENROUTER_API_KEY")
    secret_key: str = Field(alias="SECRET_KEY")

    file_tools_enabled: str | None = Field(default=None, alias="FILE_TOOLS_ENABLED")
    file_tools_root: str | None = Field(default=None, alias="FILE_TOOLS_ROOT")

    langfuse_public_key: str | None = Field(default=None, alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str | None = Field(default=None, alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="https://cloud.langfuse.com", alias="LANGFUSE_HOST")

    mcp_example_server_url: str | None = Field(default=None, alias="MCP_EXAMPLE_SERVER_URL")

    environment: str = Field(default="development", alias="ENVIRONMENT")

    @field_validator("secret_key")
    @classmethod
    def _validate_secret_key_length(cls, value: str) -> str:
        if len(value) < SECRET_KEY_MIN_LENGTH:
            raise ValueError(
                f"SECRET_KEY must be at least {SECRET_KEY_MIN_LENGTH} characters long "
                f"(got {len(value)}); a short/weak key is unsafe for signing sessions/cookies."
            )
        return value

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: str) -> str:
        normalized = value.strip().strip("'").strip('"')
        parsed = urlparse(normalized)
        if not parsed.scheme or not parsed.hostname:
            raise ValueError(
                "DATABASE_URL must include a scheme and hostname (e.g. "
                "'postgresql://user:pass@host:5432/db')."
            )
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_file_tools_enabled(self) -> bool:
        if self.file_tools_enabled is not None:
            normalized = self.file_tools_enabled.strip()
            if normalized not in ("true", "false"):
                logger.warning(
                    "FILE_TOOLS_ENABLED has an unrecognized value; treating as disabled (fail-closed).",
                    extra={
                        "event": "file_tools_enabled_unrecognized_value",
                        "raw_value": self.file_tools_enabled,
                    },
                )
        return self.file_tools_enabled == "true"

    @property
    def file_tools_allowed_root(self) -> Path:
        return Path(self.file_tools_root or Path.cwd()).resolve()

    @property
    def normalized_database_url(self) -> str:
        return self.database_url.strip().strip("'").strip('"')

    @property
    def database_host(self) -> str | None:
        parsed = urlparse(self.normalized_database_url)
        return parsed.hostname


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
