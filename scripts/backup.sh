#!/usr/bin/env bash
set -e

# Backup directory setup
BACKUP_DIR="data/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
DEST_DIR="${BACKUP_DIR}/backup_${TIMESTAMP}"

mkdir -p "${DEST_DIR}"

echo "=========================================="
echo " Starting Agentic Job Assistant Backup..."
echo " Timestamp: ${TIMESTAMP}"
echo " Dest: ${DEST_DIR}"
echo "=========================================="

# 1. Backup SQLite database if exists
if [ -f "data/jobs.db" ]; then
    echo "Backing up SQLite database..."
    cp "data/jobs.db" "${DEST_DIR}/jobs.db"
fi

# 2. Backup PostgreSQL database if container is running
if command -v docker >/dev/null 2>&1 && docker ps | grep -q job_agent_postgres; then
    echo "Dumping PostgreSQL database from container..."
    docker exec job_agent_postgres pg_dump -U jobuser jobdb > "${DEST_DIR}/postgres_dump.sql"
fi

# 3. Archive candidate application documents and memories
echo "Archiving application files and candidate memory..."
if [ -d "data/applications" ]; then
    cp -r "data/applications" "${DEST_DIR}/"
fi

if [ -f "data/resume.md" ]; then
    cp "data/resume.md" "${DEST_DIR}/"
fi

if [ -f "data/career_memory.json" ]; then
    cp "data/career_memory.json" "${DEST_DIR}/"
fi

# Create tarball archive
TARBALL="${BACKUP_DIR}/job_agent_backup_${TIMESTAMP}.tar.gz"
tar -czf "${TARBALL}" -C "${BACKUP_DIR}" "backup_${TIMESTAMP}"
rm -rf "${DEST_DIR}"

echo "=========================================="
echo " Backup Completed Successfully!"
echo " Archive path: ${TARBALL}"
echo " Size: $(du -h "${TARBALL}" | cut -f1)"
echo "=========================================="
