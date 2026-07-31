#!/bin/bash
set -e
CONTAINER=hr_agent_postgres

# Replace the catch-all "host all all all scram-sha-256" rule with
# "hostssl" so every remote connection MUST use TLS - plain-text password
# auth over an unencrypted socket is rejected outright.
docker exec "$CONTAINER" sh -c "sed -i 's/^host all all all scram-sha-256/hostssl all all all scram-sha-256/' /var/lib/postgresql/data/pg_hba.conf"
docker exec "$CONTAINER" cat /var/lib/postgresql/data/pg_hba.conf | grep -v '^#' | grep -v '^$'

docker exec "$CONTAINER" psql -U hr_agent -d hr_agent -c "SELECT pg_reload_conf();"
echo "pg_hba.conf updated to require SSL for all remote connections."
