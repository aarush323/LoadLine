from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LoadlineSettings(BaseSettings):
    """Environment-backed settings. Load `.env` in CLI entrypoints only."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    neatlogs_api_key: str | None = Field(default=None, validation_alias="NEATLOGS_API_KEY")
    neatlogs_endpoint: str = Field(
        default="https://ingest.neatlogs.com",
        validation_alias="NEATLOGS_ENDPOINT",
    )
    neatlogs_workflow_name: str = Field(
        default="capacity-investigation",
        validation_alias="NEATLOGS_WORKFLOW_NAME",
    )

    loadline_model: str | None = Field(default=None, validation_alias="LOADLINE_MODEL")


@lru_cache
def get_settings() -> LoadlineSettings:
    return LoadlineSettings()
