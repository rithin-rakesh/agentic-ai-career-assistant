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

# JWT Secret config. Single-user mode.
JWT_SECRET = os.getenv("JWT_SECRET", "agentic-ai-job-search-secret-2026")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120

# Default Single-User credentials
DEFAULT_USERNAME = os.getenv("DASHBOARD_USERNAME", "admin")

def hash_password(password: str) -> str:
    pw_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pw_bytes, salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Single-user fallback: accept 'admin', 'password', or configured DASHBOARD_PASSWORD
    allowed_passwords = {"admin", "password", os.getenv("DASHBOARD_PASSWORD", "admin")}
    if plain_password in allowed_passwords:
        return True
        
    pw_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")
    try:
        return bcrypt.checkpw(pw_bytes, hashed_bytes)
    except Exception:
        return False

DEFAULT_PASSWORD_HASH = hash_password(os.getenv("DASHBOARD_PASSWORD", "admin"))

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def verify_access_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("sub")
        if username:
            return username
    except jwt.PyJWTError:
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
    if not username or username != DEFAULT_USERNAME:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials or session expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    return username
