from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone

from fastapi import HTTPException
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from backend.cache_db import get_admin_session_secret, get_user_by_email, is_admin_email
from backend.api.core import SESSION_TTL
from backend.settings import get_env, get_required_env


# TODO(testing-only): remove once real @icscompute.com accounts are available
# to test with -- lets one personal Gmail account through the domain check.
TESTING_EMAIL_ALLOWLIST = {"akrambaasir@gmail.com"}


def _allowed_email_domain() -> str:
    # Domain Google Workspace yang diizinkan login.
    return get_env("ALLOWED_EMAIL_DOMAIN", "icscompute.com").strip().lower()


def _is_allowed_login_email(email: str) -> bool:
    # Email yang boleh dipakai login: domain Workspace resmi, atau daftar
    # testing-only di atas.
    clean_email = email.strip().lower()
    if clean_email in TESTING_EMAIL_ALLOWLIST:
        return True
    return clean_email.endswith("@" + _allowed_email_domain())


def _verify_google_id_token(token: str) -> dict[str, str]:
    # Verifikasi ID token Google di server, jangan pernah percaya klaim dari client saja.
    try:
        claims = google_id_token.verify_oauth2_token(
            token, google_requests.Request(), get_required_env("GOOGLE_CLIENT_ID")
        )
    except ValueError as error:
        raise HTTPException(status_code=401, detail="Invalid Google token.") from error

    email = str(claims.get("email", "")).strip().lower()
    name = str(claims.get("name") or email.split("@")[0]).strip()
    if email in TESTING_EMAIL_ALLOWLIST:
        return {"email": email, "name": name}

    domain = _allowed_email_domain()
    hosted_domain = str(claims.get("hd", "")).strip().lower()
    if (
        not claims.get("email_verified")
        or hosted_domain != domain
        or not email.endswith("@" + domain)
    ):
        raise HTTPException(
            status_code=403, detail=f"Only @{domain} Google Workspace accounts are allowed."
        )

    return {"email": email, "name": name}


def _session_secret() -> str:
    # Ambil secret penanda tangan token sesi.
    return get_admin_session_secret()


def _base64url_encode(value: bytes) -> str:
    # Encode bytes ke base64 URL-safe tanpa padding.
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    # Decode base64 URL-safe yang mungkin tanpa padding.
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _sign_session_payload(payload: str) -> str:
    # Buat signature HMAC untuk payload sesi.
    return hmac.new(
        _session_secret().encode("utf-8"),
        payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def _create_session_token(email: str, name: str, role: str) -> tuple[str, datetime]:
    # Buat token sesi bertanda tangan (admin atau user biasa) dengan waktu kedaluwarsa.
    expires_at = datetime.now(timezone.utc) + SESSION_TTL
    payload = _base64url_encode(
        json.dumps(
            {"email": email, "name": name, "role": role, "exp": int(expires_at.timestamp())},
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return f"{payload}.{_sign_session_payload(payload)}", expires_at


def _verify_session_token(authorization: str) -> dict[str, object]:
    # Validasi bearer token dan kembalikan identitas user jika valid.
    scheme, _, token = authorization.strip().partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Login required.")

    payload, separator, signature = token.partition(".")
    if not separator or not payload or not signature:
        raise HTTPException(status_code=401, detail="Invalid session.")
    if not hmac.compare_digest(signature, _sign_session_payload(payload)):
        raise HTTPException(status_code=401, detail="Invalid session.")

    try:
        data = json.loads(_base64url_decode(payload).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, binascii.Error) as error:
        raise HTTPException(status_code=401, detail="Invalid session.") from error

    email = str(data.get("email", "")).strip().lower()
    expires_at = int(data.get("exp", 0))
    if not email or expires_at <= int(time.time()):
        raise HTTPException(status_code=401, detail="Session expired.")

    user = get_user_by_email(email)
    if user is None:
        raise HTTPException(status_code=401, detail="Session expired.")

    # Re-check admin status against the live DB so a demoted admin's still-valid
    # token can't keep acting as admin.
    role = "admin" if user["is_admin"] else "user"
    return {"id": user["id"], "email": email, "name": user["name"], "role": role}


def _require_user(authorization: str) -> dict[str, object]:
    # Lindungi endpoint dengan verifikasi sesi login apa pun (user atau admin).
    return _verify_session_token(authorization)


def _require_admin(authorization: str) -> dict[str, object]:
    # Lindungi endpoint dengan verifikasi sesi admin.
    user = _require_user(authorization)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user


DOWNLOAD_TICKET_TTL_SECONDS = 60


def _download_ticket_secret() -> str:
    # Kunci HMAC terpisah dari yang menandatangani session token, supaya
    # sebuah download ticket yang bocor tidak bisa dipakai ulang sebagai
    # bearer token biasa (_verify_session_token pakai secret yang beda).
    return hmac.new(
        _session_secret().encode("utf-8"),
        b"download-ticket",
        hashlib.sha256,
    ).hexdigest()


def _sign_download_ticket_payload(payload: str) -> str:
    return hmac.new(
        _download_ticket_secret().encode("utf-8"),
        payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def _create_download_ticket(email: str, document_path: str, kind: str) -> str:
    # Ticket sekali-pakai berumur pendek (default 60 detik) yang cuma berlaku
    # untuk satu document_path + kind ("citation" atau "document") tertentu --
    # dipakai lewat query param di <a href> supaya bocor lewat access log/
    # browser history tidak sekritis session token 12 jam yang bisa dipakai
    # untuk semua endpoint.
    expires_at = int(time.time()) + DOWNLOAD_TICKET_TTL_SECONDS
    payload = _base64url_encode(
        json.dumps(
            {"email": email, "path": document_path, "kind": kind, "exp": expires_at},
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return f"{payload}.{_sign_download_ticket_payload(payload)}"


def _verify_download_ticket(ticket: str, document_path: str, kind: str) -> dict[str, object]:
    payload, separator, signature = ticket.partition(".")
    if not separator or not payload or not signature:
        raise HTTPException(status_code=401, detail="Invalid or expired download link.")
    if not hmac.compare_digest(signature, _sign_download_ticket_payload(payload)):
        raise HTTPException(status_code=401, detail="Invalid or expired download link.")

    try:
        data = json.loads(_base64url_decode(payload).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, binascii.Error) as error:
        raise HTTPException(status_code=401, detail="Invalid or expired download link.") from error

    expires_at = int(data.get("exp", 0))
    if (
        str(data.get("path", "")) != document_path
        or str(data.get("kind", "")) != kind
        or expires_at <= int(time.time())
    ):
        raise HTTPException(status_code=401, detail="Invalid or expired download link.")

    email = str(data.get("email", "")).strip().lower()
    user = get_user_by_email(email)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired download link.")
    return {"id": user["id"], "email": email, "name": user["name"]}


def _require_user_or_ticket(
    authorization: str, ticket: str, document_path: str, kind: str
) -> dict[str, object]:
    # Endpoint download dibuka lewat navigasi <a href> biasa oleh browser,
    # yang tidak bisa menyertakan header Authorization -- terima download
    # ticket khusus lewat query param sebagai fallback untuk kasus itu saja.
    if authorization:
        return _verify_session_token(authorization)
    if not ticket:
        raise HTTPException(status_code=401, detail="Login required.")
    return _verify_download_ticket(ticket, document_path, kind)


__all__ = [
    "_verify_google_id_token",
    "_create_session_token",
    "_verify_session_token",
    "_require_user",
    "_require_admin",
    "_create_download_ticket",
    "_require_user_or_ticket",
    "_allowed_email_domain",
    "_is_allowed_login_email",
    "is_admin_email",
]
