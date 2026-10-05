from datetime import datetime, timedelta, timezone
import hashlib
import base64
import bcrypt, jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from .database import get_db
from .models import User
from .settings import settings

SESSION_COOKIE = "campus_session"
bearer_auth = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    material = base64.urlsafe_b64encode(hashlib.sha256(password.encode("utf-8")).digest())
    return bcrypt.hashpw(material, bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        material = base64.urlsafe_b64encode(hashlib.sha256(password.encode("utf-8")).digest())
        return bcrypt.checkpw(material, hashed.encode())
    except ValueError:
        return False


def create_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user.id),
            "ver": user.token_version,
            "iat": now,
            "exp": now + timedelta(minutes=settings.access_token_minutes),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_auth),
    db: Session = Depends(get_db),
) -> User:
    error = HTTPException(
        status_code=401,
        detail="Invalid or expired credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token = (credentials.credentials if credentials else None) or request.cookies.get(
            SESSION_COOKIE
        )
        if not token:
            raise ValueError("Missing credentials")
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        uid = int(claims["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise error
    user = db.get(User, uid)
    if not user or not user.active or claims.get("ver") != user.token_version:
        raise error
    return user


def require_roles(*roles: str):
    def check(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "Insufficient permissions")
        return user

    return check
