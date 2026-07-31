#!/bin/bash
set -e
cd /home/ec2-user/Internship/Capstone

echo "Running alembic upgrade head via a temporary python container on the capstone network..."
docker run --rm \
  --network capstone_default \
  -v "$(pwd)":/repo \
  -w /repo \
  -e DATABASE_URL="postgresql+psycopg://hr_agent:${POSTGRES_PASSWORD_ARG}@postgres:5432/hr_agent" \
  python:3.12-slim \
  bash -c "pip install --quiet 'SQLAlchemy==2.0.36' 'psycopg[binary]==3.2.3' 'alembic==1.14.0' 'python-dotenv>=1.1.0' && python -m alembic upgrade head"
