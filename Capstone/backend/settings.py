from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT_DIR / ".env"
_ENV_LOADED = False


def load_capstone_env() -> None:
    # Muat file .env root sekali saja per proses.
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    load_dotenv(ENV_FILE)
    _ENV_LOADED = True


def get_required_env(name: str) -> str:
    # Ambil env wajib atau tampilkan error yang jelas.
    load_capstone_env()
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} must be set in {ENV_FILE}")
    return value


def get_env(name: str, default: str) -> str:
    # Ambil env dengan fallback string yang sudah dirapikan.
    load_capstone_env()
    return os.getenv(name, default).strip() or default


def get_int_env(name: str, default: int) -> int:
    # Ambil env integer dengan validasi.
    raw_value = get_env(name, str(default))
    try:
        return int(raw_value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be an integer in {ENV_FILE}") from error


def get_float_env(name: str, default: float) -> float:
    # Ambil env float dengan validasi.
    raw_value = get_env(name, str(default))
    try:
        return float(raw_value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be a number in {ENV_FILE}") from error
