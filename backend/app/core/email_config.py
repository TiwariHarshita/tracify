from functools import lru_cache
from typing import Literal

from pydantic import EmailStr, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmailSettings(BaseSettings):
    smtp_host: str = "127.0.0.1"
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_security: Literal["plain", "starttls", "ssl"] = "plain"
    smtp_username: str | None = None
    smtp_password: str | None = None
    mail_from: EmailStr = "noreply@example.com"
    smtp_timeout_seconds: int = Field(default=10, ge=1, le=60)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_transport(self):
        if bool(self.smtp_username) != bool(self.smtp_password):
            raise ValueError("Set both SMTP_USERNAME and SMTP_PASSWORD")
        if self.smtp_security == "plain" and self.smtp_host not in {
            "localhost", "127.0.0.1", "::1", "mailpit"
        }:
            raise ValueError("Plain SMTP is allowed only for local development")
        if self.smtp_security == "plain" and self.smtp_username:
            raise ValueError("SMTP credentials require TLS")
        return self


@lru_cache
def get_email_settings() -> EmailSettings:
    return EmailSettings()
