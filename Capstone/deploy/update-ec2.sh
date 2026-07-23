#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

show_failure_logs() {
  status=$?
  echo
  echo "Deployment gagal. Log terakhir:"
  docker compose logs --tail=150 --no-color app 9router || true
  exit "$status"
}
trap show_failure_logs ERR

echo "Validating Docker Compose configuration..."
docker compose config --quiet

echo "Building and recreating Capstone services..."
docker compose up -d --build --force-recreate
docker compose ps

echo "Checking 9Router and Kiro completion from the app container..."
docker compose exec -T app python - <<'PY'
import json
import os
import time
import urllib.error
import urllib.request


def read_json(url, *, payload=None, api_key="", timeout=60):
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        url,
        data=None if payload is None else json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="GET" if payload is None else "POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body)
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{url} returned HTTP {error.code}: {body}") from error


health_url = "http://9router:20128/api/health"
for attempt in range(30):
    try:
        status, health = read_json(health_url, timeout=5)
        if status == 200 and health.get("ok") is True:
            break
    except Exception:
        if attempt == 29:
            raise
        time.sleep(2)
else:
    raise RuntimeError("9Router health check did not become ready")

base_url = os.environ["CHAT_BASE_URL"].rstrip("/")
api_key = os.environ.get("CHAT_API_KEY", "").strip()
model = os.environ["MODEL"].strip()
flowchart_api_key = os.environ.get("FLOWCHART_API_KEY", "").strip()

if not api_key:
    raise RuntimeError("CHAT_API_KEY is empty")
if not flowchart_api_key:
    raise RuntimeError("FLOWCHART_API_KEY is empty")

_, models_response = read_json(
    f"{base_url}/models",
    api_key=api_key,
    timeout=30,
)
model_ids = {
    item.get("id")
    for item in models_response.get("data", [])
    if isinstance(item, dict)
}
if model not in model_ids:
    raise RuntimeError(
        f"Configured MODEL {model!r} is not present in the 9Router model list"
    )

status, completion = read_json(
    f"{base_url}/chat/completions",
    api_key=api_key,
    timeout=120,
    payload={
        "model": model,
        "messages": [{"role": "user", "content": "Balas tepat: pong"}],
        "max_tokens": 16,
        "temperature": 0,
        "stream": False,
    },
)
choices = completion.get("choices") or []
content = (
    choices[0].get("message", {}).get("content", "")
    if choices and isinstance(choices[0], dict)
    else ""
)
if status != 200 or not str(content).strip():
    raise RuntimeError(f"9Router returned an empty completion: {completion}")

print("9Router health: OK")
print(f"Model available: {model}")
print(f"Chat completion: {str(content).strip()}")
PY

echo "Checking the public website query endpoint..."
curl --fail --silent --show-error --max-time 180 \
  http://127.0.0.1:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question":"Apa itu HRIS?","conversation_id":"ec2-smoke"}'
echo
echo "Deployment and smoke tests completed successfully."
