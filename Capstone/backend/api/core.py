from __future__ import annotations

import sys
import threading
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.settings import load_capstone_env

ROOT_DIR = Path(__file__).resolve().parents[2]
load_capstone_env()
CREW_SRC_DIR = ROOT_DIR / "backend" / "researcher_crew" / "src"
if str(CREW_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(CREW_SRC_DIR))


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    from backend.observability import log_startup_status, shutdown

    log_startup_status()
    try:
        yield
    finally:
        shutdown()


app = FastAPI(title="ICS Knowledge Assistant API", version="1.0.0", lifespan=lifespan)
FRONTEND_DIR = ROOT_DIR / "frontend" / "web"
ASSETS_DIR = FRONTEND_DIR / "assets"
EMBEDDABLE_EXTENSIONS = {".pdf", ".docx", ".txt"}
FORM_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xls"}
LIBRARY_EXTENSIONS = EMBEDDABLE_EXTENSIONS | FORM_EXTENSIONS
MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
SESSION_TTL = timedelta(hours=12)
MAX_CONVERSATION_TURNS = 10
MAX_CONVERSATION_MESSAGES = MAX_CONVERSATION_TURNS * 2
MAX_CONVERSATION_CONTEXT_CHARS = 12000
CONVERSATION_LOCK = threading.Lock()
FAQ_LOCK = threading.Lock()
REINDEX_LOCK = threading.Lock()
ADMIN_CONFIG_LOCK = threading.RLock()

if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
