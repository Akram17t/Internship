#!/bin/bash
set -e
cd /home/ec2-user/Internship/Capstone

if grep -q "^POSTGRES_PASSWORD=" .env.production; then
  echo ".env.production already has POSTGRES_PASSWORD, skipping append."
else
  cat >> .env.production <<'ENVEOF'

# --- PostgreSQL (analytics dashboard copy; production app stays on SQLite) ---
# DATABASE_BACKEND is intentionally NOT set here - the app keeps using
# SQLite (backend/cache_db.py's default) until an explicit, separate
# cutover decision is made. This Postgres instance is a migrated copy used
# only for the analytics dashboard / Looker Studio, read via a read-only role.
POSTGRES_PASSWORD=CathngDcv4UvWTZU64g8cMTd9FH1b0xx
DATABASE_URL=postgresql+psycopg://hr_agent:CathngDcv4UvWTZU64g8cMTd9FH1b0xx@postgres:5432/hr_agent
DATABASE_POOL_SIZE=5
DATABASE_MAX_OVERFLOW=5
ANALYTICS_PSEUDONYM_SECRET=4f95bc671dbb4e7ec8f1a3c0dae34878c7a391505e39dbd54a98c1f72f20a004
ENVEOF
  echo "Appended PostgreSQL settings to .env.production"
fi

echo "--- .env.production (DATABASE/POSTGRES/ANALYTICS lines only) ---"
grep -E "^(POSTGRES_|DATABASE_|ANALYTICS_)" .env.production
