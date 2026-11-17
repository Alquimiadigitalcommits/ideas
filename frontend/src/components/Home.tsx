import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Project, SystemInfo } from "../api/types";
import { fmtTime } from "../lib/format";

interface Props {
  system: SystemInfo | null;
  onAuto: () => void;
  onManual: () => void;
  onOpen: (id: string) => void;
}

export function Home({ system, onAuto, onManual, onOpen }: Props) {
  const [projects, setProjects] = useState<Project[]>([]);
  useEffect(() => { api.listProjects().then(setProjects).catch(() => {}); }, []);
  const hw = system?.hardware;

  return (
    <div className="home">
      <div className="home-hero">
        <h1>Smart<b>Video</b>Editor</h1>
        <p className="muted">Sube un video y recíbelo editado: sin silencios, con subtítulos y en el formato de cada red.</p>
      </div>
      <div className="home-actions">
        <button className="home-card primary" onClick={onAuto}>
          <span className="hc-icon">✨</span>
          <b>Crear video automático</b>
          <span>3 pasos: video, plataforma y estilo. El programa hace el resto.</span>
          <span className="hc-tag">Recomendado</span>
        </button>
        <button className="home-card" onClick={onManual}>
          <span className="hc-icon">🎬</span>
          <b>Editar manualmente</b>
          <span>Línea de tiempo, cortes, transiciones y audio a tu gusto.</span>
        </button>
      </div>
      {system?.whisper_error && (
        <div className="banner error static home-banner"><b>Subtítulos no disponibles:</b> {system.whisper_error}</div>
      )}
      {projects.length > 0 && (
        <>
          <h2 className="home-sub">Proyectos recientes</h2>
          <div className="home-projects">
            {projects.slice(0, 8).map((p) => (
              <button key={p.id} className="home-project" onClick={() => onOpen(p.id)}>
                <b>{p.name}</b>
                <span className="muted small">
                  {p.doc.media ? `${fmtTime(p.doc.media.duration, false)} · ${p.doc.captions.length} subtítulos · ${p.doc.cuts.length} cortes` : "Sin video"}
                </span>
                <span className="muted small">{new Date(p.updated_at * 1000).toLocaleString("es")}</span>
              </button>
            ))}
          </div>
        </>
      )}
      {hw && (
        <p className="muted small home-hw">
          Este equipo: {hw.threads} hilos, {hw.ram_gb} GB de RAM → ajustes {hw.tier === "modesto" ? "rápidos para equipo modesto" : "normales"}
          {" "}(transcripción “{hw.whisper_model}”, exportación “{hw.export_preset}”).
        </p>
      )}
    </div>
  );
}
