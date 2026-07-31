#!/bin/bash
set -e
TS=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="/home/ec2-user/db_backups"
mkdir -p "$BACKUP_DIR"
# Copy the live app_state.db out of the named volume via a throwaway
# container that mounts the same volume read-only - avoids touching the
# running app container.
docker run --rm \
  -v capstone_app_storage:/app/storage:ro \
  -v "$BACKUP_DIR":/backup \
  alpine cp /app/storage/app_state.db "/backup/app_state_$TS.db"
ls -la "$BACKUP_DIR"
echo "Backup saved: $BACKUP_DIR/app_state_$TS.db"
