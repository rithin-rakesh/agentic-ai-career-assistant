# Agentic AI Career Assistant

A multi-service **Personal Autonomous AI Career Assistant** powered by **LangGraph multi-agent orchestration**, **FastAPI**, **Qdrant Vector RAG**, **PostgreSQL**, **Redis Worker Queues**, **Prometheus & Grafana Observability**, and **Docker Compose**.

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

### Automated End-to-End Execution Sequence
```
Scheduler Daemon → Collect Live Jobs → Normalize → Deduplicate → Store (PostgreSQL)
  ↓
RAG Vector Retrieval (Qdrant) → AI Matching & Scoring → Career Strategy Evaluation
  ↓
Generate Tailored Resume (PDF/Markdown) → Generate Tailored Cover Letter
  ↓
Send Instant / Daily Email Alerts (Gmail SMTP) → Update Web Control Center → Sleep
```

---

## ⚡ Quick Start with Docker Compose

Docker Compose provides the application services. Review environment variables, authentication, and integration credentials before deployment.

```bash
# 1. Clone repository
git clone https://github.com/rithin-rakesh/agentic-ai-career-assistant.git
cd agentic-ai-career-assistant

# 2. Start full stack cluster
docker compose up -d --build

# 3. Access Web Dashboard
open http://localhost/ (or http://SERVER_IP/)
```

**Security:** Never expose the dashboard publicly with default credentials. Set a strong, unique administrator password and configure secrets securely before deployment.

---

## 📥 Installation (Local Development)

To run locally without Docker:

```bash
# 1. Create Virtual Environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .\.venv\Scripts\activate

# 2. Install Dependencies
pip install -r requirements.txt

# 3. Run FastAPI Application
uvicorn app.api.app:app --reload --port 8000
```

Access local app at: `http://127.0.0.1:8000`

---

## ⚙️ Configuration & User Setup

### 1. Gemini AI Configuration
Configure your Gemini or OpenAI API credentials directly in the Dashboard under `/settings` or in `.env`:
- **Gemini API Key**: Obtain from Google AI Studio (`https://aistudio.google.com/`)
- **Primary Model**: Select `gemini-2.5-flash` or `gemini-1.5-pro`
- **Hyperparameters**: Temperature (e.g. `0.2`), Max Tokens (e.g. `2048`), Request Timeout (e.g. `30` seconds)

### 2. Email Configuration (Gmail SMTP)
Configure Gmail SMTP notifications in `/settings`:
- **SMTP Host**: `smtp.gmail.com`
- **SMTP Port**: `587` (TLS) or `465` (SSL)
- **Sender Username**: Your Gmail address (`yourname@gmail.com`)
- **App Password**: Generate a 16-character App Password via Google Account Security (`https://myaccount.google.com/apppasswords`)
- **Recipient Email**: Target email address for daily reports
- **Actions**: Click **Validate Connection** to verify handshake or **Send Test Email** to verify delivery.

### 3. Resume Upload & Vector Indexing
Upload your resume in PDF, Markdown, or Plain Text via `/settings`:
- **PDF Upload**: Select or drag a `.pdf` file.
- **Automated Workflow**: Text extraction (`pypdf`), section chunking (`ResumeChunkGenerator`), batch vector embedding generation (`EmbeddingService`), and Qdrant database ingestion (`VectorStore`).
- **File Hashing**: SHA-256 hash checks prevent unnecessary re-indexing if the resume file hasn't changed.

### 4. Job Preferences & Scheduler Controls
Configure job targeting and background sync in `/settings`:
- **Target Roles**: `AI Engineer`, `ML Architect`, `Data Scientist`, etc.
- **Target Locations**: `Remote`, `San Francisco`, `Bangalore`, etc.
- **Work Mode Toggles**: Remote, Hybrid, Onsite checkboxes
- **Salary & Experience**: Salary range bounds and Experience Level dropdown
- **Scheduler Frequency**: Select `1 hour`, `2 hours`, `4 hours`, `6 hours`, `12 hours`, or `24 hours`
- **Scheduler Controls**: `Start Agent`, `Pause Agent`, `Resume Agent`, `Run Now`, `Restart Scheduler`

---

## 🚀 Deployment Guide

### Deployment Targets
Optimized for:
1. **Oracle Cloud Always Free VM** (Ampere ARM 4-core / 24GB RAM or x86_64)
2. **Ubuntu Server** (20.04 / 22.04 / 24.04 LTS)
3. **Personal Desktop / Local Server**

### Deployment Steps on Ubuntu / Oracle Cloud
```bash
# 1. Update system & install Docker
sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io docker-compose-v2 git

# 2. Clone repository & start
git clone <repository_url>
cd job_agent
sudo docker compose up -d --build

# 3. Verify health
curl http://localhost/health
```

---

## 🛠️ Troubleshooting Guide

| Issue | Cause | Resolution |
|-------|-------|------------|
| **Login Error 500** | Missing JWT cookie / parameter binding | Access `/login` and submit `admin` / `admin`. |
| **Qdrant DB Lock / Error** | Parallel file access | In tests or standalone mode, `VECTOR_DB_URL` uses `:memory:`. In Docker, Qdrant typically runs as a standalone service on port `6333`. |
| **SMTP Auth Failed (535)** | Invalid password | Use a 16-character Gmail App Password instead of regular login password. |
| **PDF Text Extraction Empty** | Scanned PDF image | Ensure PDF contains selectable vector text. Plain text or Markdown uploads can also be used as fallbacks. |
| **Port 80 Conflict** | Nginx or local web server | Change host port mapping in `docker-compose.yml` (e.g. `"8080:80"`). |

---

## 🧪 Testing & Verification

Run the full pytest verification suite (61 unit, integration, and infrastructure tests):
```bash
pytest tests/ -v
```

---

## 📄 License
See the repository's license file for applicable terms. Do not assume an open-source license unless one has been explicitly added.
