import { useMemo } from "react";
import type { ProjectDoc } from "../api/types";
import { fmtTime } from "../lib/format";
import { keepSegments, outputDuration, toOutput } from "../lib/timemap";

interface Props {
  doc: ProjectDoc;
  videoRef: React.RefObject<HTMLVideoElement>;
  currentTime: number;
  playing: boolean;
  applyCuts: boolean;
  setApplyCuts: (v: boolean) => void;
}

export function Transport({ doc, videoRef, currentTime, playing, applyCuts, setApplyCuts }: Props) {
  const dur = doc.media?.duration ?? 0;
  const fps = doc.media?.fps || 30;
  const segs = useMemo(() => keepSegments(doc.cuts, dur), [doc.cuts, dur]);
  const outDur = outputDuration(segs);
  const outT = toOutput(segs, currentTime);

  const seek = (t: number) => {
    const v = videoRef.current;
    if (v) v.currentTime = Math.max(0, Math.min(dur, t));
  };
  const toggle = () => {
    const v = videoRef.current;
    if (!v) return;
    v.paused ? v.play().catch(() => {}) : v.pause();
  };

  return (
    <div className="transport">
      <div className="transport-buttons">
        <button className="icon-btn" title="Inicio (Home)" onClick={() => seek(0)}>⏮</button>
        <button className="icon-btn" title="−1 frame (,)" onClick={() => seek(currentTime - 1 / fps)}>◂|</button>
        <button className="icon-btn" title="−1 s (←)" onClick={() => seek(currentTime - 1)}>⏪</button>
        <button className="icon-btn play" title="Reproducir / pausa (Espacio)" onClick={toggle}>{playing ? "❚❚" : "▶"}</button>
        <button className="icon-btn" title="+1 s (→)" onClick={() => seek(currentTime + 1)}>⏩</button>
        <button className="icon-btn" title="+1 frame (.)" onClick={() => seek(currentTime + 1 / fps)}>|▸</button>
        <button className="icon-btn" title="Final (End)" onClick={() => seek(dur)}>⏭</button>
      </div>
      <div className="transport-time">
        <span className="tc">{fmtTime(currentTime)}</span>
        <span className="muted"> / {fmtTime(dur)} fuente</span>
        <span className="sep">·</span>
        <span className={outT === null ? "tc cut" : "tc"}>{outT === null ? "en corte" : fmtTime(outT)}</span>
        <span className="muted"> / {fmtTime(outDur)} salida</span>
      </div>
      <label className="toggle" title="Saltar los fragmentos eliminados al reproducir">
        <input type="checkbox" checked={applyCuts} onChange={(e) => setApplyCuts(e.target.checked)} />
        <span>Aplicar cortes</span>
      </label>
    </div>
  );
}
