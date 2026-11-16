import { useState } from "react";
import { api, ApiError } from "../api/client";
import type { Project } from "../api/types";

/** Se muestra cuando el video original ya no está en su ruta (proyecto movido o importado). */
export function RelinkPanel({ project, onDone }: { project: Project; onDone: () => void }) {
  const [path, setPath] = useState("");
  const [error, setError] = useState<string | null>(null);

  const go = async (force = false) => {
    setError(null);
    try {
      await api.relink(project.id, path.trim(), force);
      onDone();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        if (confirm(`${e.message}\n\n¿Usarlo de todas formas?`)) return go(true);
        return;
      }
      setError((e as Error).message);
    }
  };

  return (
    <div className="dropzone">
      <div className="dz-icon">⚠</div>
      <h2>No se encuentra el video original</h2>
      <p className="muted">Ruta guardada: <code>{project.doc.media?.source_path}</code></p>
      <p className="muted small">Indica dónde está ahora. Se conservan cortes, subtítulos, estilo, transiciones y audio.</p>
      <div className="row gap-s dz-path" style={{ marginTop: 0 }}>
        <input type="text" placeholder="/nueva/ruta/al/video.mp4" value={path} onChange={(e) => setPath(e.target.value)} />
        <button className="btn primary" disabled={!path.trim()} onClick={() => go()}>Reconectar</button>
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
