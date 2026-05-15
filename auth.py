import os
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database import get_db
from models import User

from dotenv import load_dotenv
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key-for-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return password_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_context.verify(plain_password, hashed_password)


def create_access_token(subject: str) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES,
    )
    payload: dict[str, Any] = {"sub": subject, "exp": expires_at}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


class AuthenticationError(Exception):
    """Raised when authentication fails. Handled globally in main.py."""

    def __init__(self, message: str = "Invalid or missing token"):
        self.message = message
        super().__init__(message)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError()

    try:
        payload = jwt.decode(
            credentials.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise AuthenticationError()
    except InvalidTokenError as exc:
        raise AuthenticationError() from exc

    user = await db.get(User, int(user_id))
    if user is None:
        raise AuthenticationError()
    return user
