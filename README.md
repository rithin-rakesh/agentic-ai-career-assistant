# Agentic AI Career Assistant — Version 1.0 Live Release Candidate

Production-grade **Personal Autonomous AI Career Assistant** powered by **LangGraph multi-agent orchestration**, **FastAPI**, **Qdrant Vector RAG**, **PostgreSQL**, **Redis Worker Queues**, **Prometheus & Grafana Observability**, and **Docker Compose**.

---

## 🏗️ System Architecture

```
                               ┌─────────────┐
                               │ User / Web  │
                               └──────┬──────┘
                                      │
                              ┌───────▼───────┐
                              │  Nginx Proxy  │ (Port 80)
                              └───────┬───────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                                   │
           ┌────────▼────────┐                 ┌────────▼────────┐
           │ FastAPI Web App │                 │ Celery Worker   │
           └────────┬────────┘                 └────────┬────────┘
                    │                                   │
      ┌─────────────┼─────────────┬─────────────┐       │
      │             │             │             │       │
┌─────▼────┐  ┌─────▼────┐  ┌─────▼────┐  ┌─────▼────┐  │
│PostgreSQL│  │ Qdrant   │  │  Redis   │  │Prometheus│◄─┘
│  (5432)  │  │  (6333)  │  │  (6379)  │  │  (9090)  │
└──────────┘  └──────────┘  └──────────┘  └─────┬────┘
                                                │
                                          ┌─────▼────┐
                                          │ Grafana  │
                                          │  (3000)  │
                                          └──────────┘
```

---

## ⚡ Deployment & Startup Guide

### 1. Production Startup (Docker Compose)
To launch the full production cluster loading `.env.production`:

```bash
# 1. Clone repository
git clone <repository_url>
cd job_agent

# 2. Copy production environment template
cp .env.production .env

# 3. Launch container stack
docker compose up -d --build
```
Access dashboard at `http://localhost/` (or `http://SERVER_IP/`).

### 2. Local Development Startup
To run locally in virtual environment mode:

```bash
# 1. Create & activate environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .\.venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy development environment template
cp .env.development .env

# 4. Launch FastAPI server
uvicorn app.api.app:app --reload --port 8000
```
Access local dashboard at `http://127.0.0.1:8000`.

---

## ⚙️ Environment Variables Matrix

| Variable | Default Value | Description / Purpose |
|----------|---------------|-----------------------|
| `ENVIRONMENT` | `production` | Deployment mode tag (`development`, `production`). |
| `DATABASE_URL` | `postgresql://...` | Database connection URI (PostgreSQL or SQLite). |
| `POSTGRES_PASSWORD` | `prod_secure_db_password` | PostgreSQL database user password. |
| `VECTOR_DB_URL` | `http://qdrant:6333` | Qdrant vector database HTTP API URL. |
| `REDIS_URL` | `redis://redis:6379/0` | Redis task queue broker URL. |
| `GEMINI_API_KEY` | *(Empty)* | Google Gemini API Key from AI Studio. |
| `MOCK_COLLECTOR` | `False` | Toggle between live HTTP scraping and simulated jobs. |
| `MOCK_LLM` | `False` | Toggle between live LLM queries and simulated evaluations. |
| `SMTP_HOST` | `smtp.gmail.com` | SMTP host for email report dispatches. |
| `SMTP_PORT` | `587` | SMTP port (587 TLS / 465 SSL). |
| `SMTP_USERNAME` | *(Empty)* | Gmail sender email address. |
| `SMTP_PASSWORD` | *(Empty)* | 16-character Gmail App Password. |
| `SECRET_KEY` | *(Random String)* | JWT session signing secret. |
| `GF_SECURITY_ADMIN_PASSWORD` | `admin` | Grafana dashboard administrator password. |

---

## 💾 Backup & Disaster Recovery Procedure

### 1. PostgreSQL Database Backup
To perform an on-demand SQL dump of all jobs, applications, and logs:
```bash
docker exec -t job_agent_postgres pg_dump -U jobuser -d jobdb > backup_jobdb_$(date +%Y%m%d_%H%M%S).sql
```

To restore a database snapshot:
```bash
cat backup_jobdb.sql | docker exec -i job_agent_postgres psql -U jobuser -d jobdb
```

### 2. Qdrant Vector Storage Backup
To snapshot vector embeddings and resume chunks:
```bash
curl -X POST http://localhost:6333/collections/resume_chunks/snapshots
```
Snapshots are persisted inside the named volume `qdrant_data`.

---

## 📊 Health Endpoints & Observability

- **System Health Dashboard**: `http://localhost/system-status`
- **JSON Health API**: `http://localhost/health`
- **Prometheus Metrics Counter**: `http://localhost/metrics` (or `http://localhost:9090`)
- **Grafana Monitoring Dashboard**: `http://localhost:3000` (Login: `admin` / `${GF_SECURITY_ADMIN_PASSWORD}`)

---

## 🛠️ Troubleshooting Guide

| Issue | Cause | Resolution |
|-------|-------|------------|
| **Login Error 500** | Missing JWT cookie / parameter binding | Access `/login` and submit `admin` / `admin`. |
| **Qdrant Connection Error** | Service boot delay | Check `docker compose logs qdrant`. Qdrant healthcheck ensures port 6333 is ready. |
| **SMTP Auth Failed (535)** | Invalid credentials | Use a 16-character Gmail App Password instead of regular login password. |
| **PDF Extraction Empty** | Scanned image PDF | Use text-selectable PDF or paste Markdown directly in Dashboard settings. |

---

## 🧪 Testing & Verification

Run the full Pytest test suite (61 unit, integration, and infrastructure tests):
```bash
pytest tests/ -v
```

---

## 📄 License
MIT License. Free for personal and commercial usage.
