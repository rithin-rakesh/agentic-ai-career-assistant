import os
import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
import bcrypt
from app.config import settings
from app.logger import logger

# OAuth2 scheme for Swagger UI auth testing
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120

# Default Single-User credentials
DEFAULT_USERNAME = settings.DASHBOARD_USERNAME

def get_jwt_secret() -> str:
    return settings.JWT_SECRET or os.getenv("JWT_SECRET", "agentic-ai-job-search-secret-2026")

def hash_password(password: str) -> str:
    pw_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pw_bytes, salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    clean_pw = plain_password.strip() if plain_password else ""
    if not clean_pw:
        return False

    # In production mode, strictly verify via bcrypt and configured password only
    if settings.ENVIRONMENT.lower() == "production":
        custom_password = settings.DASHBOARD_PASSWORD or os.getenv("DASHBOARD_PASSWORD")
        if custom_password and clean_pw == custom_password:
            return True
        try:
            return bcrypt.checkpw(clean_pw.encode("utf-8"), hashed_password.encode("utf-8"))
        except Exception:
            return False

    # Development fallback
    allowed_passwords = {"admin", "admin123", "password", settings.DASHBOARD_PASSWORD or "admin"}
    if clean_pw in allowed_passwords:
        return True
        
    try:
        return bcrypt.checkpw(clean_pw.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

DEFAULT_PASSWORD_HASH = hash_password(settings.DASHBOARD_PASSWORD or os.getenv("DASHBOARD_PASSWORD", "admin"))

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
    to_encode.update({
        "iat": now,
        "nbf": now,
        "exp": expire,
        "iss": "agentic-career-assistant"
    })
    encoded_jwt = jwt.encode(to_encode, get_jwt_secret(), algorithm=JWT_ALGORITHM)
    return encoded_jwt

def verify_access_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(
            token, 
            get_jwt_secret(), 
            algorithms=[JWT_ALGORITHM],
            options={"verify_exp": True}
        )
        username: str = payload.get("sub")
        if username:
            return username
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, jwt.PyJWTError):
        pass
    return None

def get_current_user(request: Request, header_token: Optional[str] = Depends(oauth2_scheme)) -> str:
    """
    Dependency to verify access tokens.
    Attempts to read from the Authorization Header first, falling back to Cookie validation.
    """
    token = None
    
    # 1. Try header
    if header_token:
        token = header_token
    else:
        # 2. Try cookie (standard for HTML page navigation)
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Access token missing.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    username = verify_access_token(token)
    if not username or username != settings.DASHBOARD_USERNAME:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials or session expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    return username
