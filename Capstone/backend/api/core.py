from __future__ import annotations

import sys
import threading
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.settings import load_capstone_env

ROOT_DIR = Path(__file__).resolve().parents[2]
load_capstone_env()
CREW_SRC_DIR = ROOT_DIR / "backend" / "researcher_crew" / "src"
if str(CREW_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(CREW_SRC_DIR))

app = FastAPI(title="ICS Knowledge Assistant API", version="1.0.0")
FRONTEND_DIR = ROOT_DIR / "frontend" / "web"
ASSETS_DIR = FRONTEND_DIR / "assets"
EMBEDDABLE_EXTENSIONS = {".pdf", ".docx", ".txt"}
LIBRARY_EXTENSIONS = EMBEDDABLE_EXTENSIONS | {".xlsx"}
MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
ADMIN_SESSION_TTL = timedelta(hours=12)
MAX_CONVERSATIONS = 50
MAX_CONVERSATION_TURNS = 5
MAX_CONVERSATION_MESSAGES = MAX_CONVERSATION_TURNS * 2
MAX_CONVERSATION_CONTEXT_CHARS = 3200
CONVERSATION_TTL = timedelta(days=1)
CONVERSATION_LOCK = threading.Lock()
FAQ_LOCK = threading.Lock()
REINDEX_LOCK = threading.Lock()
ADMIN_CONFIG_LOCK = threading.Lock()

if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
