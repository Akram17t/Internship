#!/bin/bash
set -e
cd /home/ec2-user/Internship/Capstone

python3 - <<'PYEOF'
path = "docker-compose.yml"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

old_block = '''  postgres:
    image: postgres:16-alpine
    container_name: hr_agent_postgres
    env_file:
      - .env.production
    environment:
      POSTGRES_USER: hr_agent
      POSTGRES_DB: hr_agent
    ports:
      - "0.0.0.0:5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U hr_agent -d hr_agent"]
      interval: 5s
      timeout: 5s
      retries: 10
    restart: unless-stopped'''

new_block = '''  postgres:
    image: postgres:16-alpine
    container_name: hr_agent_postgres
    env_file:
      - .env.production
    environment:
      POSTGRES_USER: hr_agent
      POSTGRES_DB: hr_agent
    command:
      - "-c"
      - "ssl=on"
      - "-c"
      - "ssl_cert_file=/etc/postgres_tls/server.crt"
      - "-c"
      - "ssl_key_file=/etc/postgres_tls/server.key"
    ports:
      - "0.0.0.0:5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - /home/ec2-user/postgres_tls:/etc/postgres_tls:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U hr_agent -d hr_agent"]
      interval: 5s
      timeout: 5s
      retries: 10
    restart: unless-stopped'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Updated postgres service with SSL config.")
elif "ssl_cert_file" in content:
    print("SSL config already present, no changes made.")
else:
    print("WARNING: could not find expected postgres block to update. No changes made.")
PYEOF

echo "--- postgres service block ---"
sed -n '/^  postgres:/,/^volumes:/p' docker-compose.yml
