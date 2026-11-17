import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { AutoRequest, Job, Project, SubtitleStyle, SystemInfo } from "../api/types";
import { cssScale } from "../lib/fonts";
import { fmtBytes, fmtTime } from "../lib/format";
import { SUBTITLE_PRESETS } from "../lib/presets";

interface Props {
  system: SystemInfo | null;
  projectId: string | null;           // si viene del editor, el video ya está cargado
  onProject: (id: string) => void;    // proyecto creado en el paso 1
  onOpenEditor: (id: string) => void;
  onHome: () => void;
}

type Step = "video" | "platform" | "style" | "running" | "done" | "error";

const PLATFORMS: { key: string; label: string; hint: string; aspect: string }[] = [
  { key: "tiktok", label: "TikTok", hint: "Vertical 9:16", aspect: "9:16" },
  { key: "reels", label: "Instagram Reels", hint: "Vertical 9:16", aspect: "9:16" },
  { key: "shorts", label: "YouTube Shorts", hint: "Vertical 9:16", aspect: "9:16" },
  { key: "youtube", label: "YouTube", hint: "Horizontal 16:9", aspect: "16:9" },
  { key: "instagram_square", label: "Instagram feed", hint: "Cuadrado 1:1", aspect: "1:1" },
];

const STEP_LABEL: Record<string, string> = {
  analizar: "Analizar el video", transcribir: "Escribir los subtítulos", silencios: "Quitar silencios",
  encuadre: "Seguir el rostro", exportar: "Exportar el video final",
};

const OK_EXT = [".mp4", ".mov", ".mkv"];

function AspectBox({ aspect }: { aspect: string }) {
  const [w, h] = aspect === "9:16" ? [27, 48] : aspect === "16:9" ? [56, 32] : [40, 40];
  return <span className="wz-aspect" style={{ width: w, height: h }} />;
}

function PresetPreview({ st, label, active, onClick }: { st: Partial<SubtitleStyle>; label: string; active: boolean; onClick: () => void }) {
  const size = (st.font_size ?? 64) * 0.36 * cssScale(st.font_family ?? "Inter");
  const words = (st.uppercase ? "ASÍ SE VERÁN" : "Así se verán").split(" ");
  return (
    <button className={"wz-preset" + (active ? " active" : "")} onClick={onClick}>
      <div className="wz-preset-stage">
        <span style={{ fontFamily: `"${st.font_family}", sans-serif`, fontSize: size, fontWeight: st.bold ? 800 : 500,
          color: st.primary_color, WebkitTextStroke: `${Math.max(1, (st.outline_width ?? 3) * 0.5)}px ${st.outline_color}`,
          paintOrder: "stroke fill" }}>
          {words.map((w, i) => (
            <span key={i} style={i === 1 && st.highlight_words ? { color: st.highlight_color } : undefined}>{w} </span>
          ))}
        </span>
      </div>
      <b>{label}</b>
    </button>
  );
}

export function AutoWizard({ system, projectId, onProject, onOpenEditor, onHome }: Props) {
  const [step, setStep] = useState<Step>(projectId ? "platform" : "video");
  const [pid, setPid] = useState<string | null>(projectId);
  const [project, setProject] = useState<Project | null>(null);
  const [upload, setUpload] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const [platform, setPlatform] = useState("tiktok");
  const [preset, setPreset] = useState("impacto");
  const [opts, setOpts] = useState({ subtitles: true, remove_silences: true, pace: "dinamico" as "natural" | "dinamico",
    face_track: true, enhance_audio: true });
  const [job, setJob] = useState<Job | null>(null);
  const [musicName, setMusicName] = useState<string | null>(null);
  const started = useRef(0);
  const fileInput = useRef<HTMLInputElement>(null);
  const musicInput = useRef<HTMLInputElement>(null);
  const whisperError = system?.whisper_error ?? null;
  const hw = system?.hardware;

  useEffect(() => {
    if (!pid) return;
    api.getProject(pid).then((p) => {
      setProject(p);
      if (p.doc.audio.music) setMusicName(p.doc.audio.music.file_name);
    }).catch(() => {});
  }, [pid]);

  // seguimiento del proceso
  useEffect(() => {
    if (step !== "running" || !job) return;
    const t = window.setInterval(async () => {
      try {
        const j = await api.job(job.id);
        setJob(j);
        if (j.status === "done") setStep("done");
        else if (j.status === "failed" || j.status === "canceled") setStep("error");
      } catch { /* reintenta en el siguiente ciclo */ }
    }, 700);
    return () => window.clearInterval(t);
  }, [step, job?.id]);

  const sendVideo = async (file: File) => {
    setError(null);
    if (!OK_EXT.some((e) => file.name.toLowerCase().endsWith(e))) return setError("Ese formato no sirve. Usa un video MP4, MOV o MKV.");
    try {
      const p = await api.createProject(file.name.replace(/\.[^.]+$/, ""));
      setUpload(0);
      await api.importFile(p.id, file, setUpload, false);
      setPid(p.id);
      onProject(p.id);
      setProject(await api.getProject(p.id));
      setStep("platform");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUpload(null);
    }
  };

  const sendMusic = async (file: File) => {
    if (!pid) return;
    try {
      await api.uploadMusic(pid, file);
      setMusicName(file.name);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const start = async () => {
    if (!pid || !project) return;
    setError(null);
    const base = project.doc.subtitle_style;
    const { label: _label, ...st } = SUBTITLE_PRESETS[preset];
    void _label;
    const req: AutoRequest = {
      platform, remove_silences: opts.remove_silences, pace: opts.pace,
      subtitles: opts.subtitles && !whisperError, burn_subtitles: true,
      subtitle_style: { ...base, ...st, preset } as SubtitleStyle,
      face_track: opts.face_track, enhance_audio: opts.enhance_audio, language: "es",
    };
    try {
      const j = await api.auto(pid, req);
      started.current = Date.now();
      setJob(j);
      setStep("running");
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const m = project?.doc.media;
  const msg = job?.message ?? "";
  const stepMatch = msg.match(/Paso (\d+) de (\d+)/);
  const current = stepMatch ? Number(stepMatch[1]) : 0;
  const steps: string[] = useMemo(() => {
    const out = ["analizar"];
    const sameAspect = m && PLATFORMS.find((p) => p.key === platform)?.aspect ===
      (Math.abs(m.width / m.height - 16 / 9) < 0.06 ? "16:9" : Math.abs(m.width / m.height - 1) < 0.06 ? "1:1" :
        Math.abs(m.width / m.height - 9 / 16) < 0.06 ? "9:16" : "otro");
    const hasWords = !!project?.doc.captions.some((c) => c.words.length);
    if (m?.has_audio && (opts.subtitles || opts.remove_silences) && !hasWords) out.push("transcribir");
    if (m?.has_audio && opts.remove_silences) out.push("silencios");
    if (opts.face_track && !sameAspect) out.push("encuadre");
    out.push("exportar");
    return out;
  }, [m, platform, opts, project]);
  const resultSteps: string[] = job?.result?.steps ?? steps;
  const progress = job?.progress ?? 0;
  const elapsed = (Date.now() - started.current) / 1000;
  const eta = progress > 0.04 ? (elapsed * (1 - progress)) / progress : null;
  const res = job?.result;
  const ex = res?.export;

  return (
    <div className="wizard">
      <header className="wz-head">
        <button className="btn ghost small" onClick={onHome}>← Inicio</button>
        <ol className="wz-steps">
          {[["video", "1. Tu video"], ["platform", "2. Plataforma"], ["style", "3. Estilo"], ["running", "4. Listo"]].map(([k, l]) => {
            const order = ["video", "platform", "style", "running"];
            const idx = order.indexOf(step === "done" || step === "error" ? "running" : step);
            const me = order.indexOf(k);
            return <li key={k} className={me < idx ? "done" : me === idx ? "current" : ""}>{l}</li>;
          })}
        </ol>
        <span className="muted small">{hw ? `Equipo ${hw.tier} · ${hw.threads} hilos · ${hw.ram_gb} GB` : ""}</span>
      </header>

      {whisperError && step !== "running" && step !== "done" && (
        <div className="banner error static">
          <b>Los subtítulos no están disponibles en este computador.</b> {whisperError}
        </div>
      )}

      {step === "video" && (
        <section className={"wz-card wz-drop" + (over ? " over" : "")}
          onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f) sendVideo(f); }}>
          <div className="dz-icon">🎬</div>
          <h1>Elige tu video</h1>
          <p className="muted">Arrástralo aquí o búscalo en tu computador. MP4, MOV o MKV.</p>
          <button className="btn primary big-cta" disabled={upload !== null} onClick={() => fileInput.current?.click()}>Buscar video</button>
          <input ref={fileInput} type="file" hidden accept=".mp4,.mov,.mkv,video/mp4,video/quicktime,video/x-matroska"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) sendVideo(f); e.target.value = ""; }} />
          {upload !== null && (
            <div className="upload-progress"><div style={{ width: `${upload * 100}%` }} /><span>Cargando video… {Math.round(upload * 100)}%</span></div>
          )}
        </section>
      )}

      {step === "platform" && (
        <section className="wz-card">
          {m && <p className="muted small">🎞 {m.file_name} · {fmtTime(m.duration, false)} · {m.width}×{m.height} · {fmtBytes(m.size_bytes)}</p>}
          <h1>¿Dónde lo vas a publicar?</h1>
          <div className="wz-platforms">
            {PLATFORMS.map((p) => (
              <button key={p.key} className={"wz-platform" + (platform === p.key ? " active" : "")} onClick={() => setPlatform(p.key)}>
                <AspectBox aspect={p.aspect} /><b>{p.label}</b><span>{p.hint}</span>
              </button>
            ))}
          </div>
          <div className="wz-nav">
            <span />
            <button className="btn primary big-cta" onClick={() => setStep("style")}>Siguiente →</button>
          </div>
        </section>
      )}

      {step === "style" && (
        <section className="wz-card">
          <h1>¿Cómo quieres los subtítulos?</h1>
          <div className="wz-presets">
            {Object.entries(SUBTITLE_PRESETS).map(([k, { label, ...st }]) => (
              <PresetPreview key={k} st={st} label={label} active={preset === k} onClick={() => setPreset(k)} />
            ))}
          </div>
          <div className="wz-options">
            <label className={"wz-opt" + (whisperError ? " disabled" : "")}>
              <input type="checkbox" checked={opts.subtitles && !whisperError} disabled={!!whisperError}
                onChange={(e) => setOpts({ ...opts, subtitles: e.target.checked })} />
              <span><b>Subtítulos automáticos</b><small>Escribe lo que dices, palabra por palabra</small></span>
            </label>
            <label className="wz-opt">
              <input type="checkbox" checked={opts.remove_silences} onChange={(e) => setOpts({ ...opts, remove_silences: e.target.checked })} />
              <span><b>Quitar silencios y pausas</b><small>Corta los momentos sin voz</small></span>
            </label>
            {opts.remove_silences && (
              <div className="wz-opt wz-pace">
                <span><b>Ritmo</b><small>Dinámico: pausas mínimas y zoom en los cortes, como en TikTok</small></span>
                <div className="segmented">
                  <button className={opts.pace === "natural" ? "active" : ""} onClick={() => setOpts({ ...opts, pace: "natural" })}>Natural</button>
                  <button className={opts.pace === "dinamico" ? "active" : ""} onClick={() => setOpts({ ...opts, pace: "dinamico" })}>Dinámico</button>
                </div>
              </div>
            )}
            <label className="wz-opt">
              <input type="checkbox" checked={opts.face_track} onChange={(e) => setOpts({ ...opts, face_track: e.target.checked })} />
              <span><b>Seguir el rostro</b><small>Mantiene tu cara en cuadro al pasar de horizontal a vertical</small></span>
            </label>
            <label className="wz-opt">
              <input type="checkbox" checked={opts.enhance_audio} onChange={(e) => setOpts({ ...opts, enhance_audio: e.target.checked })} />
              <span><b>Mejorar el audio</b><small>Quita ruido de fondo y deja el volumen estándar de redes</small></span>
            </label>
            <div className="wz-opt">
              <span><b>Música de fondo</b><small>{musicName ? `♪ ${musicName} · baja sola cuando hablas` : "Opcional. Baja sola cuando hablas"}</small></span>
              <button className="btn small" onClick={() => musicInput.current?.click()}>{musicName ? "Cambiar" : "Agregar"}</button>
              <input ref={musicInput} type="file" hidden accept=".mp3,.wav,.m4a,.aac,.ogg,.flac,.opus,audio/*"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) sendMusic(f); e.target.value = ""; }} />
            </div>
          </div>
          <div className="wz-nav">
            <button className="btn ghost" onClick={() => setStep("platform")}>← Atrás</button>
            <button className="btn primary big-cta" onClick={start}>✨ Crear mi video</button>
          </div>
        </section>
      )}

      {step === "running" && (
        <section className="wz-card wz-running">
          <h1>Creando tu video…</h1>
          <div className="wz-bar"><div style={{ width: `${Math.round(progress * 100)}%` }} /></div>
          <p className="muted">{Math.round(progress * 100)}%{eta !== null ? ` · faltan unos ${fmtTime(eta, false)}` : ""}</p>
          <ul className="wz-checklist">
            {resultSteps.map((s, i) => (
              <li key={s} className={i + 1 < current ? "done" : i + 1 === current ? "current" : ""}>
                <span className="dot">{i + 1 < current ? "✓" : i + 1 === current ? "" : ""}</span>{STEP_LABEL[s] ?? s}
              </li>
            ))}
          </ul>
          <p className="muted small">Puedes dejar esta ventana abierta y seguir usando el computador.</p>
          <button className="btn ghost" onClick={() => job && api.cancelJob(job.id).catch(() => {})}>Cancelar</button>
        </section>
      )}

      {step === "done" && ex && pid && (
        <section className="wz-card wz-done">
          <h1>¡Tu video está listo! 🎉</h1>
          <div className="wz-result">
            <video src={api.exportUrl(pid, ex.video)} controls playsInline className={`wz-video a-${ex.width >= ex.height ? (ex.width === ex.height ? "sq" : "h") : "v"}`} />
            <div className="wz-summary">
              <ul>
                <li><b>{ex.width}×{ex.height}</b> · {fmtTime(ex.duration, false)} de video</li>
                {res.removed_seconds !== undefined && <li>Se quitaron <b>{res.removed_seconds.toFixed(1)} s</b> de silencios ({res.cuts} cortes)</li>}
                {ex.cues > 0 && <li><b>{ex.cues}</b> subtítulos</li>}
                {res.face !== undefined && <li>{res.face ? "Rostro seguido automáticamente" : "No se detectó rostro: encuadre centrado"}</li>}
                <li className="muted small">Tardó {fmtTime(res.seconds, false)}</li>
              </ul>
              <a className="btn primary big-cta" href={api.exportUrl(pid, ex.video)} download>⇩ Descargar video</a>
              {ex.files?.find((f: string) => f.endsWith(".srt")) && (
                <a className="btn" href={api.exportUrl(pid, ex.files.find((f: string) => f.endsWith(".srt")))} download>⇩ Subtítulos (SRT)</a>
              )}
              <button className="btn" onClick={() => onOpenEditor(pid)}>✏️ Ajustar en el editor</button>
              <button className="btn ghost" onClick={() => { setJob(null); setStep("platform"); }}>🔁 Crear para otra plataforma</button>
            </div>
          </div>
        </section>
      )}

      {step === "error" && (
        <section className="wz-card">
          <h1>{job?.status === "canceled" ? "Proceso cancelado" : "No se pudo terminar el video"}</h1>
          {job?.error && <p className="error">{job.error.split("\n")[0]}</p>}
          <div className="wz-nav">
            {pid && <button className="btn ghost" onClick={() => onOpenEditor(pid)}>Abrir en el editor</button>}
            <button className="btn primary" onClick={() => setStep("style")}>Intentar de nuevo</button>
          </div>
        </section>
      )}

      {error && <p className="error wz-error">{error}</p>}
    </div>
  );
}
