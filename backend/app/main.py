"""Aplicación FastAPI. Sirve la API y, si existe, el frontend compilado."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, db
from .api import auto, projects, system

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app() -> FastAPI:
    config.ensure_workspace()
    db.conn()
    app = FastAPI(title="Smart Video Editor", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["*"], allow_headers=["*"])
    @app.exception_handler(config.InvalidProjectId)
    def _bad_id(_req, _exc):
        return JSONResponse(status_code=404, content={"detail": "Proyecto no encontrado"})

    app.include_router(projects.router)
    app.include_router(system.router)
    app.include_router(auto.router)

    dist = config.FRONTEND_DIST
    if dist.is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        root = dist.resolve()

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                return JSONResponse(status_code=404, content={"detail": "No encontrado"})
            # resolve() + comprobación de pertenencia: impide salir de dist/ con ../ (también codificado)
            f = (root / path).resolve()
            if path and f.is_file() and f.is_relative_to(root):
                return FileResponse(f)
            return FileResponse(root / "index.html")
    return app


app = create_app()
