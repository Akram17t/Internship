from __future__ import annotations

from backend.api.core import app

# Impor route untuk mendaftarkan seluruh endpoint ke app yang sama.
from backend.api import routes_admin as _routes_admin  # noqa: F401
from backend.api import routes_public as _routes_public  # noqa: F401

__all__ = ["app"]
