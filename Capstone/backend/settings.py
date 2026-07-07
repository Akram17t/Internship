from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT_DIR / ".env"
_ENV_LOADED = False


def load_capstone_env() -> None:
    """Load the root .env file once for the current process."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    load_dotenv(ENV_FILE)
    _ENV_LOADED = True


def get_required_env(name: str) -> str:
    """Read a required environment variable or raise a clear error."""
    load_capstone_env()
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} must be set in {ENV_FILE}")
    return value


def get_env(name: str, default: str) -> str:
    """Read an environment variable with a trimmed string fallback."""
    load_capstone_env()
    return os.getenv(name, default).strip() or default


def get_int_env(name: str, default: int) -> int:
    """Read an integer environment variable with validation."""
    raw_value = get_env(name, str(default))
    try:
        return int(raw_value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be an integer in {ENV_FILE}") from error


def get_float_env(name: str, default: float) -> float:
    """Read a float environment variable with validation."""
    raw_value = get_env(name, str(default))
    try:
        return float(raw_value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be a number in {ENV_FILE}") from error
