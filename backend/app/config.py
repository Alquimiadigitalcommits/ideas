"""Configuración global. Todo lo generado vive en WORKSPACE; los originales nunca se tocan."""
from __future__ import annotations

import os
from pathlib import Path

WORKSPACE = Path(os.environ.get("SVE_WORKSPACE", Path.home() / "SmartVideoEditor")).expanduser()
DB_PATH = WORKSPACE / "projects.sqlite3"
PROJECTS_DIR = WORKSPACE / "projects"

HOST = os.environ.get("SVE_HOST", "127.0.0.1")
PORT = int(os.environ.get("SVE_PORT", "8765"))

FFMPEG = os.environ.get("SVE_FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("SVE_FFPROBE", "ffprobe")

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv"}

# Proxy de previsualización
PROXY_MAX_HEIGHT = int(os.environ.get("SVE_PROXY_HEIGHT", "720"))

# Whisper
DEFAULT_WHISPER_MODEL = os.environ.get("SVE_WHISPER_MODEL", "base")
WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v3"]

MAX_PARALLEL_JOBS = int(os.environ.get("SVE_MAX_JOBS", "2"))

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


def project_dir(project_id: str) -> Path:
    d = PROJECTS_DIR / project_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_workspace() -> None:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
