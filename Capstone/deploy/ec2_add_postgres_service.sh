#!/bin/bash
set -e
cd /home/ec2-user/Internship/Capstone

if grep -q "^  postgres:" docker-compose.yml; then
  echo "postgres service already present in docker-compose.yml, skipping insert."
else
  # Append a postgres service + named volume, bound to 127.0.0.1 only for
  # now (safe default, matches every other service's port binding here).
  # Reads POSTGRES_PASSWORD from .env.production (added separately) so the
  # password is never hardcoded into the compose file itself.
  python3 - <<'PYEOF'
import re

path = "docker-compose.yml"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

postgres_service = """
  postgres:
    image: postgres:16-alpine
    container_name: hr_agent_postgres
    env_file:
      - .env.production
    environment:
      POSTGRES_USER: hr_agent
      POSTGRES_DB: hr_agent
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U hr_agent -d hr_agent"]
      interval: 5s
      timeout: 5s
      retries: 10
    restart: unless-stopped
"""

if "\n  postgres:" not in content:
    # Insert right before the "volumes:" top-level key.
    marker = "\nvolumes:\n"
    idx = content.index(marker)
    content = content[:idx] + postgres_service + content[idx:]
    content = content.replace(
        "volumes:\n  app_storage:\n",
        "volumes:\n  app_storage:\n  postgres_data:\n",
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Inserted postgres service into docker-compose.yml")
else:
    print("postgres service already present, no changes made")
PYEOF
fi

echo "--- docker-compose.yml (final) ---"
cat docker-compose.yml
