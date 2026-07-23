#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

docker compose up -d 9router 9router-loopback app

echo "Starting Kiro AWS Builder ID device login..."
echo

docker compose exec -T 9router node - <<'NODE'
const crypto = require("node:crypto");
const Database = require("better-sqlite3");

const REGION = "us-east-1";
const START_URL = "https://view.awsapps.com/start";
const ISSUER_URL = "https://identitycenter.amazonaws.com/ssoins-722374e8c3c8e6c6";
const DB_PATH = "/app/data/db/data.sqlite";

async function postJson(url, body, headers = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...headers,
    },
    body: JSON.stringify(body),
  });
  const text = await response.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    data = { raw: text };
  }
  if (!response.ok) {
    throw new Error(`${url} returned HTTP ${response.status}: ${text}`);
  }
  return data;
}

function sleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function resolveProfileArn(accessToken) {
  try {
    const data = await postJson(
      "https://codewhisperer.us-east-1.amazonaws.com",
      { maxResults: 10 },
      {
        "Content-Type": "application/x-amz-json-1.0",
        "x-amz-target": "AmazonCodeWhispererService.ListAvailableProfiles",
        Authorization: `Bearer ${accessToken}`,
      },
    );
    const profiles = Array.isArray(data.profiles) ? data.profiles : [];
    const profile = profiles.find((item) => item?.arn || item?.profileArn);
    return profile?.arn || profile?.profileArn || null;
  } catch (error) {
    console.warn(`Profile lookup warning: ${error.message}`);
    return null;
  }
}

async function main() {
  const db = new Database(DB_PATH);
  db.pragma("busy_timeout = 5000");

  const existing = db.prepare(
    "SELECT id FROM providerConnections WHERE provider = ? AND isActive = 1 LIMIT 1",
  ).get("kiro");
  if (existing) {
    console.log("An active Kiro connection already exists in the EC2 database.");
    db.close();
    return;
  }

  const client = await postJson(
    `https://oidc.${REGION}.amazonaws.com/client/register`,
    {
      clientName: "kiro-oauth-client",
      clientType: "public",
      scopes: [
        "codewhisperer:completions",
        "codewhisperer:analysis",
        "codewhisperer:conversations",
      ],
      grantTypes: [
        "urn:ietf:params:oauth:grant-type:device_code",
        "refresh_token",
      ],
      issuerUrl: ISSUER_URL,
    },
  );

  const device = await postJson(
    `https://oidc.${REGION}.amazonaws.com/device_authorization`,
    {
      clientId: client.clientId,
      clientSecret: client.clientSecret,
      startUrl: START_URL,
    },
  );

  console.log("Open this URL in your browser and approve the Kiro connection:");
  console.log(device.verificationUriComplete || device.verificationUri);
  if (!device.verificationUriComplete && device.userCode) {
    console.log(`Code: ${device.userCode}`);
  }
  console.log();
  console.log("Waiting for authorization...");

  let intervalSeconds = Number(device.interval || 5);
  const deadline = Date.now() + Number(device.expiresIn || 600) * 1000;
  let tokens = null;

  while (Date.now() < deadline) {
    await sleep(intervalSeconds * 1000);
    const response = await fetch(`https://oidc.${REGION}.amazonaws.com/token`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        clientId: client.clientId,
        clientSecret: client.clientSecret,
        deviceCode: device.deviceCode,
        grantType: "urn:ietf:params:oauth:grant-type:device_code",
      }),
    });
    const data = await response.json();

    if (data.accessToken) {
      tokens = data;
      break;
    }
    if (data.error === "slow_down") {
      intervalSeconds += 5;
      continue;
    }
    if (data.error === "authorization_pending") {
      continue;
    }
    throw new Error(
      `Kiro authorization failed: ${data.error_description || data.error || "unknown error"}`,
    );
  }

  if (!tokens) {
    throw new Error("Kiro authorization timed out. Run the script again.");
  }

  const profileArn =
    tokens.profileArn || (await resolveProfileArn(tokens.accessToken));
  const now = new Date().toISOString();
  const expiresIn = Number(tokens.expiresIn || 3600);
  const connectionData = {
    accessToken: tokens.accessToken,
    refreshToken: tokens.refreshToken,
    expiresIn,
    expiresAt: new Date(Date.now() + expiresIn * 1000).toISOString(),
    tokenType: tokens.tokenType || "Bearer",
    testStatus: "active",
    providerSpecificData: {
      profileArn,
      clientId: client.clientId,
      clientSecret: client.clientSecret,
      region: REGION,
      authMethod: "builder-id",
      startUrl: START_URL,
    },
  };

  db.prepare(`
    INSERT INTO providerConnections(
      id, provider, authType, name, email, priority, isActive, data, createdAt, updatedAt
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(
    crypto.randomUUID(),
    "kiro",
    "oauth",
    "EC2 Builder ID",
    null,
    1,
    1,
    JSON.stringify(connectionData),
    now,
    now,
  );
  db.close();

  console.log("Kiro credentials saved to the EC2 9Router database.");
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
NODE

echo
echo "Testing Kiro through the Capstone app network..."
docker compose exec -T app python - <<'PY'
import json
import os
import urllib.error
import urllib.request

base_url = os.environ["CHAT_BASE_URL"].rstrip("/")
payload = json.dumps({
    "model": os.environ["MODEL"],
    "messages": [{"role": "user", "content": "Balas tepat: pong"}],
    "max_tokens": 16,
    "temperature": 0,
    "stream": False,
}).encode("utf-8")
request = urllib.request.Request(
    f"{base_url}/chat/completions",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(request, timeout=120) as response:
        body = json.loads(response.read().decode("utf-8"))
except urllib.error.HTTPError as error:
    detail = error.read().decode("utf-8", errors="replace")
    raise RuntimeError(f"9Router returned HTTP {error.code}: {detail}") from error

choices = body.get("choices") or []
content = choices[0].get("message", {}).get("content", "") if choices else ""
if not str(content).strip():
    raise RuntimeError(f"9Router returned an empty completion: {body}")
print(f"Kiro completion: {str(content).strip()}")
PY

echo
echo "Testing the public website endpoint..."
curl --fail --silent --show-error --max-time 180 \
  http://127.0.0.1:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question":"Apa itu HRIS?","conversation_id":"ec2-kiro-connected"}'
echo
echo "Kiro is connected to the EC2 9Router and Capstone is ready."
