# Production Deployment Guide – Agentic AI Career Assistant

This document outlines the production setup for running the **Agentic AI Job Search & Career Assistant** using Docker Compose.

---

## Target Deployment Environments

- **Oracle Cloud Always Free VM** (Ampere A1 / AMD x86 24GB RAM)
- **Local Ubuntu Server / Linux Workstation**
- **Desktop Environment** (Windows / macOS Docker Desktop)

---

## System Architecture & Container Topology

```
                  [ Nginx Reverse Proxy (Port 80) ]
                                 │
                 ┌───────────────┴───────────────┐
                 │                               │
        [ FastAPI App (8000) ]        [ Celery Worker ]
                 │                               │
    ┌────────────┼────────────┐           ┌──────┴──────┐
    │            │            │           │             │
[PostgreSQL]  [Qdrant]     [Redis]   [PostgreSQL]    [Qdrant]
   (5432)      (6333)       (6379)      (5432)        (6333)
                 │
                 ├──> [Prometheus (9090)] ──> [Grafana (3000)]
```

### Services Matrix

| Service | Port | Description |
|---------|------|-------------|
| `app` | `8000` | FastAPI Web Dashboard, REST API & LangGraph Orchestration |
| `worker` | - | Celery background task queue worker |
| `postgres` | `5432` | PostgreSQL 15 database |
| `redis` | `6379` | Redis 7 broker & cache |
| `qdrant` | `6333` | Qdrant vector search engine |
| `nginx` | `80` | Nginx reverse proxy |
| `prometheus` | `9090` | Prometheus metrics scraper |
| `grafana` | `3000` | Grafana visual analytics dashboards (admin / admin) |

---

## Deployment Steps

### 1. Prerequisites

Ensure Docker and Docker Compose are installed:
```bash
docker --version
docker-compose --version
```

### 2. Environment Configuration

Clone repository and configure `.env`:
```bash
cp .env.example .env
```

Update your `.env` settings:
```dotenv
DATABASE_URL=postgresql://jobuser:jobpassword@postgres:5432/jobdb
VECTOR_DB_URL=http://qdrant:6333
REDIS_URL=redis://redis:6379/0
USE_CELERY=True
OPENAI_API_KEY=your_key_here
```

### 3. Launch Services

Start the container cluster in background mode:
```bash
docker-compose up -d --build
```

### 4. Verify Health

Check container status and health:
```bash
docker-compose ps
```

Test health endpoint:
```bash
curl http://localhost/health
```

---

## Database Migrations (Alembic)

Run database migrations inside the app container:
```bash
docker-compose exec app alembic upgrade head
```

---

## Accessing Services

- **Web Control Dashboard**: `http://<SERVER_IP>/` (or `http://localhost/`)
- **Analytics & Preference Curves**: `http://<SERVER_IP>/analytics`
- **Prometheus Scraper**: `http://<SERVER_IP>:9090/`
- **Grafana Metrics Dashboard**: `http://<SERVER_IP>:3000/` (User: `admin`, Pass: `admin`)
- **Health Check**: `http://<SERVER_IP>/health`
- **Prometheus Metrics Endpoint**: `http://<SERVER_IP>/metrics`

---

## Backup & Restore

Generate an automated backup:
```bash
make backup
# or
bash scripts/backup.sh
```

Backups are saved as compressed archives under `data/backups/job_agent_backup_<timestamp>.tar.gz`.
