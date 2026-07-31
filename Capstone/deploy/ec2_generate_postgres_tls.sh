#!/bin/bash
set -e
cd /home/ec2-user/Internship/Capstone

CERT_DIR="/home/ec2-user/postgres_tls"
mkdir -p "$CERT_DIR"

if [ ! -f "$CERT_DIR/server.crt" ]; then
  # Self-signed cert is sufficient here: it still encrypts the connection
  # (protects credentials/data in transit), which is the goal - it does not
  # provide certificate-authority-verified server identity. Looker
  # Studio/Data Studio's PostgreSQL connector accepts this with SSL mode
  # "require" (encrypt, don't verify CA).
  openssl req -new -x509 -days 3650 -nodes \
    -out "$CERT_DIR/server.crt" \
    -keyout "$CERT_DIR/server.key" \
    -subj "/CN=hr-agent-postgres"
  chmod 600 "$CERT_DIR/server.key"
  chmod 644 "$CERT_DIR/server.crt"
  echo "Generated self-signed TLS cert at $CERT_DIR"
else
  echo "TLS cert already exists at $CERT_DIR, skipping generation."
fi

ls -la "$CERT_DIR"
