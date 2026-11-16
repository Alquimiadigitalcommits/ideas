import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Project } from "../api/types";
import { fmtTime } from "../lib/format";

interface Props {
  currentId: string | null;
  onOpen: (id: string | null) => void;
  refreshKey: number;
}

export function ProjectsPanel({ currentId, onOpen, refreshKey }: Props) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = () => api.listProjects().then(setProjects).catch((e) => setError(e.message));
  useEffect(() => { load(); }, [refreshKey, currentId]);

  const create = async () => {
    const p = await api.createProject(`Proyecto ${new Date().toLocaleDateString("es")} ${new Date().toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" })}`);
    await load();
    onOpen(p.id);
  };
  const remove = async (p: Project) => {
    if (!confirm(`¿Borrar "${p.name}"? Se eliminan sus proxies y exportaciones. El video original no se toca.`)) return;
    await api.deleteProject(p.id);
    if (p.id === currentId) onOpen(null);
    load();
  };

  return (
    <aside className="projects">
      <header>
        <h2>Proyectos</h2>
        <button className="btn primary small" onClick={create}>+ Nuevo</button>
      </header>
      {error && <p className="error small">{error}</p>}
      <ul>
        {projects.map((p) => (
          <li key={p.id} className={p.id === currentId ? "active" : ""} onClick={() => onOpen(p.id)}>
            <div className="p-name">{p.name}</div>
            <div className="p-meta">
              {p.doc.media ? `${p.doc.media.file_name} · ${fmtTime(p.doc.media.duration, false)}` : "Sin video"}
            </div>
            <div className="p-meta">{new Date(p.updated_at * 1000).toLocaleString("es")}</div>
            <button className="p-del" title="Borrar proyecto" onClick={(e) => { e.stopPropagation(); remove(p); }}>✕</button>
          </li>
        ))}
        {projects.length === 0 && <li className="empty muted small">Crea tu primer proyecto.</li>}
      </ul>
    </aside>
  );
}
