#!/bin/bash
set -e
cd /home/ec2-user/Internship/Capstone

sed -i 's/"0.0.0.0:5432:5432"/"127.0.0.1:5432:5432"/' docker-compose.yml
grep -B2 -A1 '5432:5432' docker-compose.yml

docker compose up -d postgres
sleep 5
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
