import os
import pytest
from datetime import timedelta
from fastapi.testclient import TestClient
from app.config import Settings
from app.auth.authentication import (
    create_access_token, verify_access_token, verify_password, hash_password
)
from app.logger import SecretMaskingFilter, sanitize_secret_text
from app.api.app import app

client = TestClient(app)

def test_production_config_validation_failure():
    """
    Verifies that validate_production_config raises ValueError when running in production mode
    with insecure default development keys.
    """
    insecure_settings = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="dev_secret_key_change_in_production_32bytes_min",
        JWT_SECRET="agentic-ai-job-search-secret-2026"
    )
    with pytest.raises(ValueError) as exc_info:
        insecure_settings.validate_production_config()
    assert "Production Configuration Validation Failed" in str(exc_info.value)

def test_production_config_validation_success():
    """
    Verifies that validate_production_config succeeds when running in production mode
    with strong randomly generated keys.
    """
    secure_settings = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e",
        JWT_SECRET="4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b"
    )
    # Should not raise exception
    secure_settings.validate_production_config()

def test_jwt_token_lifecycle():
    """
    Verifies JWT token encoding, claim payload, and signature validation.
    """
    username = "admin"
    token = create_access_token(data={"sub": username})
    assert token is not None
    verified_user = verify_access_token(token)
    assert verified_user == username

def test_jwt_token_expiration():
    """
    Verifies expired JWT tokens are rejected.
    """
    username = "admin"
    expired_token = create_access_token(
        data={"sub": username}, 
        expires_delta=timedelta(seconds=-10)
    )
    verified_user = verify_access_token(expired_token)
    assert verified_user is None

def test_secure_cookies_attributes():
    """
    Verifies login response sets HttpOnly and SameSite cookie parameters.
    """
    response = client.post(
        "/login",
        data={"username": "admin", "password": "admin"},
        follow_redirects=False
    )
    assert response.status_code in [303, 302]
    cookie_header = response.headers.get("set-cookie", "")
    assert "access_token=" in cookie_header
    assert "httponly" in cookie_header.lower()
    assert "samesite=lax" in cookie_header.lower()

def test_security_headers_middleware():
    """
    Verifies required security headers are injected into all HTTP responses.
    """
    response = client.get("/health")
    assert response.status_code == 200
    headers = response.headers
    assert headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-XSS-Protection") == "1; mode=block"
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "Content-Security-Policy" in headers

def test_cors_origin_restriction():
    """
    Verifies CORS headers honor allowed origins configuration.
    """
    response = client.options(
        "/api/jobs/",
        headers={
            "Origin": "http://localhost:8000",
            "Access-Control-Request-Method": "GET"
        }
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:8000"

def test_log_secret_masking():
    """
    Verifies SecretMaskingFilter redacts sensitive information from log strings.
    """
    sample_log = "API_KEY=AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5 PWD=secretpassword123 Bearer eyJhbGciOiJIUzI1NiJ9.test.sig"
    sanitized = sanitize_secret_text(sample_log)
    assert "AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5" not in sanitized
    assert "secretpassword123" not in sanitized
    assert "••••••••" in sanitized
