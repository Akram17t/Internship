#!/bin/bash
set -e
cd /home/ec2-user/Internship/Capstone

MODE_FLAG="$1"

echo "Running migrator ($MODE_FLAG) via temporary python container..."
docker run --rm \
  --network capstone_default \
  -v "$(pwd)":/repo \
  -v capstone_app_storage:/app_storage \
  -w /repo \
  -e DATABASE_URL="postgresql+psycopg://hr_agent:${POSTGRES_PASSWORD_ARG}@postgres:5432/hr_agent" \
  -e DATABASE_BACKEND=postgres \
  python:3.12-slim \
  bash -c "pip install --quiet 'SQLAlchemy==2.0.36' 'psycopg[binary]==3.2.3' 'python-dotenv>=1.1.0' 'fastapi>=0.116.0' && python -m backend.scripts.migrate_to_postgres --sqlite-path /app_storage/app_state.db $MODE_FLAG"
