import os
import pytest
from fastapi.testclient import TestClient
from app.api.app import app
from app.config import settings

client = TestClient(app)

def test_metrics_endpoint():
    """
    Verifies that the /metrics endpoint returns Prometheus formatted metrics.
    """
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "job_agent_http_requests_total" in response.text

def test_correlation_id_middleware_header():
    """
    Verifies that requests return an X-Correlation-ID header.
    """
    response = client.get("/health")
    assert response.status_code == 200
    assert "x-correlation-id" in response.headers

def test_dockerfile_and_compose_files_exist():
    """
    Verifies presence of critical deployment files.
    """
    base_dir = settings.BASE_DIR
    assert os.path.exists(os.path.join(base_dir, "Dockerfile"))
    assert os.path.exists(os.path.join(base_dir, "docker-compose.yml"))
    assert os.path.exists(os.path.join(base_dir, ".dockerignore"))
    assert os.path.exists(os.path.join(base_dir, "nginx", "nginx.conf"))
    assert os.path.exists(os.path.join(base_dir, "monitoring", "prometheus.yml"))
    assert os.path.exists(os.path.join(base_dir, "alembic.ini"))
    assert os.path.exists(os.path.join(base_dir, "Makefile"))
