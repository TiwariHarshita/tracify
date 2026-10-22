from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    cookie_secure: bool = False
    allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:8000",
    ]

    session_secret: str = Field(min_length=32)
    backend_url: str = "http://localhost:8000"

    google_client_id: str | None = None
    google_client_secret: str | None = None

    github_client_id: str | None = None
    github_client_secret: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()