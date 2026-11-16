import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Aspect, ExportFile, ExportProfile, ExportRequest, Job, ProjectDoc } from "../api/types";
import { fmtBytes, fmtTime } from "../lib/format";
import { keepSegments, outputDuration } from "../lib/timemap";
import { Check, Section } from "./ui";

interface Props {
  projectId: string;
  doc: ProjectDoc;
  updateDoc: (fn: (d: ProjectDoc) => ProjectDoc) => void;
  profiles: Record<string, ExportProfile>;
  runExport: (r: ExportRequest) => void;
  running: boolean;
  lastExport: Job | null;
}

const SHORT_SIDES = [[720, "720p"], [1080, "1080p"], [1440, "1440p"], [2160, "4K"]] as const;

function dims(aspect: Aspect, short: number) {
  const [aw, ah] = aspect === "9:16" ? [9, 16] : aspect === "16:9" ? [16, 9] : [1, 1];
  let w: number, h: number;
  if (aw >= ah) { h = short; w = Math.round((h * aw) / ah); } else { w = short; h = Math.round((w * ah) / aw); }
  return [w - (w % 2), h - (h % 2)];
}

export function ExportPanel({ projectId, doc, updateDoc, profiles, runExport, running, lastExport }: Props) {
  const [profile, setProfile] = useState(() =>
    Object.entries(profiles).find(([, p]) => p.aspect === doc.format.aspect)?.[0] ?? "tiktok");
  const [short, setShort] = useState(1080);
  const [fps, setFps] = useState<number>(30);
  const [quality, setQuality] = useState(20);
  const [burn, setBurn] = useState(true);
  const [srt, setSrt] = useState(true);
  const [normalize, setNormalize] = useState(true);
  const [files, setFiles] = useState<ExportFile[]>([]);

  useEffect(() => { api.exports(projectId).then(setFiles).catch(() => {}); }, [projectId, lastExport?.id, lastExport?.status]);

  const chooseProfile = (key: string) => {
    setProfile(key);
    const p = profiles[key];
    setFps(p.fps);
    setShort(p.short);
    if (p.aspect !== doc.format.aspect) updateDoc((d) => ({ ...d, format: { ...d.format, aspect: p.aspect } }));
  };

  const [w, h] = dims(doc.format.aspect, short);
  const outDur = outputDuration(keepSegments(doc.cuts, doc.media?.duration ?? 0));
  const srcFps = doc.media?.fps ?? 30;

  return (
    <div className="panel-scroll">
      <Section title="Perfil de plataforma">
        <div className="profile-grid">
          {Object.entries(profiles).map(([k, p]) => (
            <button key={k} className={"profile" + (k === profile ? " active" : "")} onClick={() => chooseProfile(k)}>
              <b>{p.label}</b><span>{p.aspect} · {p.fps} fps</span>
            </button>
          ))}
        </div>
      </Section>
      <Section title="Video">
        <div className="grid2">
          <label className="field"><span>Resolución</span>
            <select value={short} onChange={(e) => setShort(Number(e.target.value))}>
              {SHORT_SIDES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className="field"><span>FPS</span>
            <select value={fps} onChange={(e) => setFps(Number(e.target.value))}>
              {[24, 25, 30, 50, 60].map((v) => <option key={v} value={v}>{v}</option>)}
              {![24, 25, 30, 50, 60].includes(srcFps) && <option value={srcFps}>{srcFps} (fuente)</option>}
            </select>
          </label>
        </div>
        <label className="field"><span>Calidad</span>
          <select value={quality} onChange={(e) => setQuality(Number(e.target.value))}>
            <option value={17}>Máxima (archivo grande)</option>
            <option value={20}>Alta (recomendada)</option>
            <option value={23}>Media (más liviano)</option>
          </select>
        </label>
        <p className="muted small">Salida: {w}×{h} · {fps} fps · {doc.format.aspect} · duración {fmtTime(outDur)}</p>
      </Section>
      <Section title="Subtítulos y audio">
        <Check label="Incrustar subtítulos en el video" checked={burn} onChange={setBurn} />
        <Check label="Generar archivo SRT" checked={srt} onChange={setSrt} />
        <Check label="Normalizar volumen (−14 LUFS, estándar de redes)" checked={normalize} onChange={setNormalize} />
        {!doc.captions.length && <small className="hint">No hay subtítulos: se exportará sin ellos.</small>}
      </Section>
      <button className="btn primary full big" disabled={running || !doc.media}
        onClick={() => runExport({ profile, width: w, height: h, fps, burn_subtitles: burn, write_srt: srt,
          normalize_audio: normalize, crf: quality, preset: "medium" })}>
        {running ? "Exportando…" : "⇩ Exportar MP4"}
      </button>

      {lastExport?.status === "done" && lastExport.result && (
        <div className="export-done">
          ✓ Exportado en {lastExport.result.width}×{lastExport.result.height}, {fmtTime(lastExport.result.duration)}
          <small className="muted">{lastExport.result.dir}</small>
        </div>
      )}

      <Section title="Archivos exportados">
        {files.length === 0 && <p className="muted small">Todavía no hay exportaciones.</p>}
        <ul className="file-list">
          {files.map((f) => (
            <li key={f.name}>
              <a href={api.exportUrl(projectId, f.name)} download>{f.name}</a>
              <span className="muted small">{fmtBytes(f.size)}</span>
            </li>
          ))}
        </ul>
        <a className="btn ghost small" href={api.projectFileUrl(projectId)} download>Guardar copia del proyecto (.json)</a>
      </Section>
    </div>
  );
}
