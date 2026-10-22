import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class EmailRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class Credentials(EmailRequest):
    password: str = Field(min_length=1, max_length=128)


class RegisterRequest(Credentials):
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name cannot be blank")
        return value


class TokenRequest(BaseModel):
    token: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")


class ResetPasswordRequest(TokenRequest):
    new_password: str = Field(min_length=12, max_length=128)


class MessageResponse(BaseModel):
    message: str


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    email_verified: bool

    model_config = ConfigDict(from_attributes=True)
