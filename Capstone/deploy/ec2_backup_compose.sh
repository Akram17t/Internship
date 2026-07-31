#!/bin/bash
set -e
cd /home/ec2-user/Internship/Capstone
TS=$(date +%Y%m%d-%H%M%S)
cp docker-compose.yml "docker-compose.yml.bak.$TS"
echo "Backed up docker-compose.yml -> docker-compose.yml.bak.$TS"
ls -la docker-compose.yml.bak*
