import { useState } from "react";
import { api } from "../api/client";
import type { Job } from "../api/types";

const LABEL: Record<string, string> = {
  prepare: "Preparación", transcribe: "Transcripción", autoedit: "Auto-edición", export: "Exportación",
  scenes: "Escenas", facetrack: "Rostro", preview: "Previsualización", auto: "Creación automática",
};

export function JobBar({ jobs, onChange }: { jobs: Job[]; onChange: () => void }) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const now = Date.now() / 1000;
  const visible = jobs.filter((j) =>
    j.status === "queued" || j.status === "running" ||
    (!dismissed.has(j.id) && j.status === "failed" && now - j.updated_at < 600));
  if (!visible.length) return null;
  return (
    <div className="jobbar">
      {visible.map((j) => (
        <div key={j.id} className={`job ${j.status}`}>
          <b>{LABEL[j.kind] ?? j.kind}</b>
          {j.status === "failed" ? (
            <span className="error grow" title={j.error ?? ""}>Error: {(j.error ?? "").split("\n")[0].slice(0, 160)}</span>
          ) : (
            <>
              <span className="grow muted">{j.message}</span>
              <div className="bar"><div style={{ width: `${Math.round(j.progress * 100)}%` }} /></div>
              <span className="pct">{Math.round(j.progress * 100)}%</span>
            </>
          )}
          {j.status === "failed" ? (
            <button className="btn tiny ghost" onClick={() => setDismissed(new Set(dismissed).add(j.id))}>Cerrar</button>
          ) : (
            <button className="btn tiny" onClick={() => api.cancelJob(j.id).then(onChange).catch(() => {})}>Cancelar</button>
          )}
        </div>
      ))}
    </div>
  );
}
