"""Persistencia SQLite: proyectos (documento JSON versionado) y jobs."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from typing import Optional

from . import config
from .schemas import Job, Project, ProjectDoc

_lock = threading.RLock()
_conn: Optional[sqlite3.Connection] = None


class RevisionConflict(Exception):
    def __init__(self, current: Project):
        super().__init__("revision conflict")
        self.current = current


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        config.ensure_workspace()
        _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY, name TEXT NOT NULL,
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                rev INTEGER NOT NULL, doc TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, project_id TEXT, kind TEXT NOT NULL,
                status TEXT NOT NULL, progress REAL NOT NULL, message TEXT NOT NULL,
                error TEXT, result TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS jobs_project ON jobs(project_id);
            """
        )
        # Jobs que quedaron vivos tras un cierre inesperado
        _conn.execute(
            "UPDATE jobs SET status='failed', error='Interrumpido: la aplicación se cerró', updated_at=? "
            "WHERE status IN ('queued','running')",
            (time.time(),),
        )
        _conn.commit()
    return _conn


def reset_connection() -> None:
    """Solo para tests (cambio de workspace)."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = None


# ---------------------------------------------------------------- proyectos

def _row_to_project(r: sqlite3.Row) -> Project:
    return Project(
        id=r["id"], name=r["name"], created_at=r["created_at"], updated_at=r["updated_at"],
        rev=r["rev"], doc=ProjectDoc.model_validate_json(r["doc"]),
    )


def create_project(name: str) -> Project:
    now = time.time()
    pid = uuid.uuid4().hex[:12]
    doc = ProjectDoc()
    with _lock:
        conn().execute(
            "INSERT INTO projects VALUES (?,?,?,?,?,?)",
            (pid, name, now, now, 1, doc.model_dump_json()),
        )
        conn().commit()
    config.project_dir(pid)
    return get_project(pid)  # type: ignore[return-value]


def list_projects() -> list[Project]:
    with _lock:
        rows = conn().execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
    return [_row_to_project(r) for r in rows]


def get_project(pid: str) -> Optional[Project]:
    with _lock:
        r = conn().execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    return _row_to_project(r) if r else None


def save_project(pid: str, doc: ProjectDoc, expected_rev: Optional[int] = None,
                 name: Optional[str] = None) -> Project:
    """Guarda el documento. Si expected_rev no coincide lanza RevisionConflict."""
    with _lock:
        cur = get_project(pid)
        if cur is None:
            raise KeyError(pid)
        if expected_rev is not None and expected_rev != cur.rev:
            raise RevisionConflict(cur)
        conn().execute(
            "UPDATE projects SET doc=?, rev=?, updated_at=?, name=? WHERE id=?",
            (doc.model_dump_json(), cur.rev + 1, time.time(), name or cur.name, pid),
        )
        conn().commit()
    return get_project(pid)  # type: ignore[return-value]


def update_doc(pid: str, mutate) -> Project:
    """Lectura-modificación-escritura atómica usada por los jobs."""
    with _lock:
        cur = get_project(pid)
        if cur is None:
            raise KeyError(pid)
        doc = cur.doc.model_copy(deep=True)
        mutate(doc)
        return save_project(pid, doc)


def delete_project(pid: str) -> None:
    with _lock:
        conn().execute("DELETE FROM projects WHERE id=?", (pid,))
        conn().execute("DELETE FROM jobs WHERE project_id=?", (pid,))
        conn().commit()


# ---------------------------------------------------------------- jobs

def _row_to_job(r: sqlite3.Row) -> Job:
    return Job(
        id=r["id"], project_id=r["project_id"], kind=r["kind"], status=r["status"],
        progress=r["progress"], message=r["message"], error=r["error"],
        result=json.loads(r["result"]) if r["result"] else None,
        created_at=r["created_at"], updated_at=r["updated_at"],
    )


def insert_job(project_id: Optional[str], kind: str, message: str = "En cola") -> Job:
    now = time.time()
    jid = uuid.uuid4().hex[:12]
    with _lock:
        conn().execute(
            "INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)",
            (jid, project_id, kind, "queued", 0.0, message, None, None, now, now),
        )
        conn().commit()
    return get_job(jid)  # type: ignore[return-value]


def update_job(jid: str, **fields) -> None:
    if "result" in fields and fields["result"] is not None:
        fields["result"] = json.dumps(fields["result"])
    fields["updated_at"] = time.time()
    cols = ", ".join(f"{k}=?" for k in fields)
    with _lock:
        conn().execute(f"UPDATE jobs SET {cols} WHERE id=?", (*fields.values(), jid))
        conn().commit()


def get_job(jid: str) -> Optional[Job]:
    with _lock:
        r = conn().execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
    return _row_to_job(r) if r else None


def list_jobs(project_id: str, limit: int = 30) -> list[Job]:
    with _lock:
        rows = conn().execute(
            "SELECT * FROM jobs WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
            (project_id, limit),
        ).fetchall()
    return [_row_to_job(r) for r in rows]
