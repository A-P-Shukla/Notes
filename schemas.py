from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class MessageResponse(BaseModel):
    message: str


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    created_at: datetime


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str


class NoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)

    @field_validator("title", "content", mode="before")
    @classmethod
    def strip_and_reject_blank(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
        if not v:
            raise ValueError("must not be blank or whitespace-only")
        return v


class NoteShareCreate(BaseModel):
    share_with_email: EmailStr


class NoteRevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    note_id: int
    title: str
    content: str
    updated_at: datetime


class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str
    created_at: datetime
    updated_at: datetime
