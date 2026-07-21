from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone

from fastapi import HTTPException

from backend.api.cache_store import _load_admin_config
from backend.api.core import ADMIN_SESSION_TTL


def _admin_records() -> list[dict[str, str]]:
    # Ambil daftar admin yang sudah terkonfigurasi.
    raw_admins = _load_admin_config().get("admins", [])
    if not isinstance(raw_admins, list):
        return []
    return [admin for admin in raw_admins if isinstance(admin, dict)]


def _find_admin(email: str) -> dict[str, str] | None:
    # Cari admin berdasarkan email ter-normalisasi.
    clean_email = email.strip().lower()
    for admin in _admin_records():
        if str(admin.get("email") or "").strip().lower() == clean_email:
            return admin
    return None


def _has_configured_admin() -> bool:
    # Pastikan minimal ada satu admin lengkap yang bisa login.
    return any(admin.get("email") and admin.get("password") for admin in _admin_records())


def _admin_session_secret() -> str:
    # Ambil secret penanda tangan token sesi admin.
    return str(_load_admin_config()["session_secret"])


def _base64url_encode(value: bytes) -> str:
    # Encode bytes ke base64 URL-safe tanpa padding.
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    # Decode base64 URL-safe yang mungkin tanpa padding.
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _sign_admin_payload(payload: str) -> str:
    # Buat signature HMAC untuk payload sesi admin.
    return hmac.new(
        _admin_session_secret().encode("utf-8"),
        payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def _create_admin_token(email: str) -> tuple[str, datetime]:
    # Buat token sesi admin bertanda tangan dengan waktu kedaluwarsa.
    expires_at = datetime.now(timezone.utc) + ADMIN_SESSION_TTL
    payload = _base64url_encode(
        json.dumps(
            {"email": email, "exp": int(expires_at.timestamp())},
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return f"{payload}.{_sign_admin_payload(payload)}", expires_at


def _verify_admin_token(authorization: str) -> str:
    # Validasi bearer token dan kembalikan email admin jika valid.
    scheme, _, token = authorization.strip().partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Admin login required.")

    payload, separator, signature = token.partition(".")
    if not separator or not payload or not signature:
        raise HTTPException(status_code=401, detail="Invalid admin session.")
    if not hmac.compare_digest(signature, _sign_admin_payload(payload)):
        raise HTTPException(status_code=401, detail="Invalid admin session.")

    try:
        data = json.loads(_base64url_decode(payload).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, binascii.Error) as error:
        raise HTTPException(status_code=401, detail="Invalid admin session.") from error

    email = str(data.get("email", "")).strip().lower()
    expires_at = int(data.get("exp", 0))
    if _find_admin(email) is None or expires_at <= int(time.time()):
        raise HTTPException(status_code=401, detail="Admin session expired.")
    return email


def _require_admin(authorization: str) -> str:
    # Lindungi endpoint dengan verifikasi token admin.
    return _verify_admin_token(authorization)
