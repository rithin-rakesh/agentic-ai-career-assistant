# Stage 1: Base Builder
FROM python:3.11-slim as builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu --prefix=/install -r requirements.txt

# Stage 2: Final Production Runtime
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    ca-certificates \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /install/bin /usr/local/bin
COPY . /app

RUN mkdir -p data/applications data/sent_emails data/qdrant_db data/generated_resumes data/generated_cover_letters data/master_resumes data/templates

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
