import { api } from "../api/client";
import type { Job } from "../api/types";
import { fmtTime } from "../lib/format";

export function PreviewModal({ projectId, job, onClose }: { projectId: string; job: Job; onClose: () => void }) {
  const r = job.result ?? {};
  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header>
          <b>Previsualización exacta</b>
          <span className="muted small">desde {fmtTime(r.start ?? 0)} · {r.duration?.toFixed(2)} s · {r.width}×{r.height} · render FFmpeg real</span>
          <button className="btn tiny ghost" onClick={onClose}>Cerrar ✕</button>
        </header>
        <video src={api.previewClipUrl(projectId, r.video)} controls autoPlay loop playsInline />
      </div>
    </div>
  );
}
