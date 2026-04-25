#!/bin/bash
# ConfiDoc — PostgreSQL Backup Script

# Configuration
BACKUP_DIR="/backups/postgres"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/confidoc_db_${TIMESTAMP}.sql.gz"
RETENTION_DAYS=30

# Load environment variables if needed
# source .env

echo "[$(date)] Starting PostgreSQL backup..."

mkdir -p "${BACKUP_DIR}"

# Run pg_dump
# We assume PGHOST, PGUSER, PGPASSWORD, PGDATABASE are set in environment
if pg_dump | gzip > "${BACKUP_FILE}"; then
    echo "[$(date)] Backup successful: ${BACKUP_FILE}"
    
    # Optional: Upload to S3/MinIO
    # aws s3 cp "${BACKUP_FILE}" s3://my-confidoc-backups/database/
    
    # Cleanup old backups
    find "${BACKUP_DIR}" -name "confidoc_db_*.sql.gz" -mtime +${RETENTION_DAYS} -delete
    echo "[$(date)] Old backups cleaned up."
else
    echo "[$(date)] ERROR: Backup failed!"
    exit 1
fi
