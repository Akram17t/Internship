from __future__ import annotations

from backend.api.auth import _create_session_token, _verify_google_id_token
from backend.api.core import app
from backend.api.models import GoogleLoginPayload, GoogleLoginResponse
from backend.cache_db import upsert_user


@app.post("/api/auth/google", response_model=GoogleLoginResponse)
def login_with_google(payload: GoogleLoginPayload) -> GoogleLoginResponse:
    # Verifikasi ID token Google, buat/perbarui user, lalu terbitkan token sesi.
    claims = _verify_google_id_token(payload.id_token)
    user = upsert_user(email=claims["email"], name=claims["name"])
    role = "admin" if user["is_admin"] else "user"
    token, expires_at = _create_session_token(user["email"], user["name"], role)
    return GoogleLoginResponse(
        email=user["email"],
        name=user["name"],
        role=role,
        token=token,
        expires_at=expires_at.isoformat(timespec="seconds"),
    )
