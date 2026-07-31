#!/bin/bash
set -e

docker exec hr_agent_postgres psql -U hr_agent -d hr_agent <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'datastudio_readonly') THEN
    CREATE ROLE datastudio_readonly WITH LOGIN PASSWORD '${READONLY_PASSWORD_ARG}';
  ELSE
    ALTER ROLE datastudio_readonly WITH PASSWORD '${READONLY_PASSWORD_ARG}';
  END IF;
END
\$\$;

GRANT CONNECT ON DATABASE hr_agent TO datastudio_readonly;
GRANT USAGE ON SCHEMA analytics TO datastudio_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO datastudio_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA analytics GRANT SELECT ON TABLES TO datastudio_readonly;

-- Explicitly no access to the app schema (contains PII: emails, chat
-- content, admin accounts, password hashes) or the migration internals.
REVOKE ALL ON SCHEMA app FROM datastudio_readonly;
REVOKE ALL ON SCHEMA public FROM datastudio_readonly;

\du datastudio_readonly
SQL

echo "Read-only role 'datastudio_readonly' ready (SELECT on analytics schema only)."
