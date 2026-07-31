#!/bin/bash
set -e
docker exec hr_agent_postgres psql -U hr_agent -d hr_agent -c "\du datastudio_readonly"
docker exec hr_agent_postgres psql -U hr_agent -d hr_agent -c "SELECT grantee, table_schema, table_name, privilege_type FROM information_schema.role_table_grants WHERE grantee='datastudio_readonly' ORDER BY table_name;"
