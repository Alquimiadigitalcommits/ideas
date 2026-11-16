import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api/client";
import type { Cut, ExportRequest, Job, SystemInfo } from "./api/types";
import { AudioPanel } from "./components/AudioPanel";
import { AutoEditPanel } from "./components/AutoEditPanel";
import { ExportPanel } from "./components/ExportPanel";
import { FormatPanel } from "./components/FormatPanel";
import { ImportDropzone } from "./components/ImportDropzone";
import { JobBar } from "./components/JobBar";
import { Monitor } from "./components/Monitor";
import { PreviewModal } from "./components/PreviewModal";
import { ProjectsPanel } from "./components/ProjectsPanel";
import { RelinkPanel } from "./components/RelinkPanel";
import { StylePanel } from "./components/StylePanel";
import { SubtitlesPanel } from "./components/SubtitlesPanel";
import { Timeline } from "./components/Timeline";
import { TransitionsPanel } from "./components/TransitionsPanel";
import { Transport } from "./components/Transport";
import { uid } from "./lib/captions";
import { fmtBytes } from "./lib/format";
import { editSegments } from "./lib/joins";
import { toOutput } from "./lib/timemap";
import { useJobs } from "./state/useJobs";
import { useProject } from "./state/useProject";

type Tab = "autoedit" | "subtitles" | "style" | "format" | "transitions" | "audio" | "export";
const TABS: [Tab, string][] = [["autoedit", "Cortes"], ["subtitles", "Subtítulos"], ["style", "Estilo"], ["format", "Formato"],
  ["transitions", "Transiciones"], ["audio", "Audio"], ["export", "Exportar"]];

const SAVE_LABEL = { saved: "Guardado ✓", dirty: "Cambios sin guardar…", saving: "Guardando…", error: "Error al guardar" };

export default function App() {
  const [projectId, setProjectId] = useState<string | null>(() => localStorage.getItem("sve.project"));
  const [showProjects, setShowProjects] = useState(true);
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [systemError, setSystemError] = useState<string | null>(null);
  const [fonts, setFonts] = useState<string[]>([]);
  const [tab, setTab] = useState<Tab>("autoedit");
  const [currentTime, setCurrentTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [applyCuts, setApplyCuts] = useState(true);
  const [selectedCut, setSelectedCut] = useState<string | null>(null);
  const [selectedCaption, setSelectedCaption] = useState<string | null>(null);
  const [markIn, setMarkIn] = useState<number | null>(null);
  const [markOut, setMarkOut] = useState<number | null>(null);
  const [assetsVersion, setAssetsVersion] = useState(0);
  const [listKey, setListKey] = useState(0);
  const [lastExport, setLastExport] = useState<Job | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [previewJob, setPreviewJob] = useState<Job | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  const { project, updateDoc, rename, flush, reload, saveState, notice, setNotice, undo, redo, canUndo, canRedo } =
    useProject(projectId);
  const doc = project?.doc;

  useEffect(() => {
    api.system().then(setSystem).catch(() => setSystemError("No se puede conectar con el motor local. ¿Está corriendo el backend?"));
    api.fonts().then(setFonts).catch(() => {});
  }, []);

  useEffect(() => {
    projectId ? localStorage.setItem("sve.project", projectId) : localStorage.removeItem("sve.project");
    setSelectedCut(null); setSelectedCaption(null); setMarkIn(null); setMarkOut(null); setCurrentTime(0); setLastExport(null);
  }, [projectId]);

  const onJobFinished = useCallback((j: Job) => {
    if (j.status === "done") {
      if (j.kind !== "export") reload();
      if (j.kind === "prepare") setAssetsVersion((v) => v + 1);
      if (j.kind === "autoedit" && j.result)
        setToast(`Auto-edición: ${j.result.cuts} cortes, −${j.result.removed_seconds} s. Revisa y recupera lo que quieras conservar.`);
      if (j.kind === "transcribe" && j.result) setToast(`Transcripción lista: ${j.result.words} palabras (${j.result.language}).`);
      if (j.kind === "export") { setLastExport(j); setToast(`Exportación lista: ${j.result?.video}`); }
      if (j.kind === "scenes" && j.result) setToast(`${j.result.scenes} cambios de escena detectados.`);
      if (j.kind === "facetrack" && j.result)
        setToast(`Rostro detectado en el ${Math.round(j.result.detection_rate * 100)} % de las muestras · ${j.result.keyframes} puntos clave.`);
      if (j.kind === "preview") setPreviewJob(j);
      setListKey((k) => k + 1);
    } else if (j.status === "canceled") setToast("Operación cancelada.");
    if (j.kind === "export") setLastExport(j);
  }, [reload]);

  const { jobs, isRunning, refresh: refreshJobs } = useJobs(projectId, onJobFinished);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 6000);
    return () => clearTimeout(t);
  }, [toast]);

  const start = async (fn: () => Promise<Job>) => {
    try {
      await flush();
      await fn();
      refreshJobs();
    } catch (e) {
      setNotice((e as Error).message);
    }
  };

  const runAutoEdit = () => doc && start(() => api.autoedit(project!.id, doc.autoedit));
  const runTranscribe = (model: string, lang: string | null) => start(() => api.transcribe(project!.id, model, lang));
  const runExport = (r: ExportRequest) => start(() => api.export(project!.id, r));
  const runScenes = (th: number) => start(() => api.scenes(project!.id, th));
  const runFaceTrack = () => start(() => api.facetrack(project!.id));
  const runPreview = (center: number) => start(() => api.previewClip(project!.id, center, 3));
  /** Cambios que hace el servidor sobre el documento (p. ej. subir música): guardar antes, recargar después. */
  const serverChange = async (fn: () => Promise<unknown>) => {
    await flush();
    await fn();
    await reload();
  };
  const updateCuts = useCallback((fn: (c: Cut[]) => Cut[]) => updateDoc((d) => ({ ...d, cuts: fn(d.cuts) })), [updateDoc]);

  const seek = useCallback((t: number) => {
    const v = videoRef.current;
    if (v) v.currentTime = t;
    setCurrentTime(t);
  }, []);

  const cutMarkedRange = useCallback(() => {
    if (markIn === null) return;
    const out = markOut ?? currentTime;
    const [s, e] = [Math.min(markIn, out), Math.max(markIn, out)];
    if (e - s < 0.05) return;
    updateCuts((cuts) => [...cuts, { id: uid(), start: s, end: e, kind: "manual" as const, enabled: true, reason: "Corte manual" }]
      .sort((a, b) => a.start - b.start));
    setMarkIn(null); setMarkOut(null);
  }, [markIn, markOut, currentTime, updateCuts]);

  const splitHere = useCallback(() => {
    updateCuts((cuts) => [...cuts, { id: uid(), start: currentTime, end: currentTime, kind: "split" as const, enabled: true,
      reason: "División manual" }].sort((a, b) => a.start - b.start));
  }, [currentTime, updateCuts]);

  // atajos de teclado
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) || !doc?.media) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); e.shiftKey ? redo() : undo(); return; }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") { e.preventDefault(); redo(); return; }
      if (e.ctrlKey || e.metaKey) return;
      const v = videoRef.current;
      const fps = doc.media.fps || 30;
      const k = e.key.toLowerCase();
      if (e.code === "Space") { e.preventDefault(); if (v) v.paused ? v.play().catch(() => {}) : v.pause(); }
      else if (e.key === "ArrowLeft") seek(Math.max(0, currentTime - (e.shiftKey ? 5 : 1)));
      else if (e.key === "ArrowRight") seek(Math.min(doc.media.duration, currentTime + (e.shiftKey ? 5 : 1)));
      else if (e.key === ",") seek(Math.max(0, currentTime - 1 / fps));
      else if (e.key === ".") seek(currentTime + 1 / fps);
      else if (e.key === "Home") seek(0);
      else if (e.key === "End") seek(doc.media.duration);
      else if (k === "i") { setMarkIn(currentTime); setMarkOut(null); }
      else if (k === "o") { if (markIn !== null) setMarkOut(currentTime); }
      else if (k === "x") cutMarkedRange();
      else if (k === "s") splitHere();
      else if (e.key === "Escape") { setMarkIn(null); setMarkOut(null); setSelectedCut(null); }
      else if ((e.key === "Delete" || e.key === "Backspace") && selectedCut)
        updateCuts((c) => c.map((x) => (x.id === selectedCut ? { ...x, enabled: !x.enabled } : x)));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [doc?.media, currentTime, markIn, selectedCut, cutMarkedRange, seek, updateCuts, undo, redo, splitHere]);

  return (
    <div className={"app" + (showProjects ? "" : " no-projects")}>
      <header className="topbar">
        <button className="icon-btn" title="Proyectos" onClick={() => setShowProjects(!showProjects)}>☰</button>
        <div className="brand">Smart<b>Video</b>Editor</div>
        {project && (
          <>
            <input className="project-name" value={project.name} onChange={(e) => rename(e.target.value)} />
            <button className="icon-btn" title="Deshacer (Ctrl+Z)" disabled={!canUndo} onClick={undo}>↶</button>
            <button className="icon-btn" title="Rehacer (Ctrl+Shift+Z)" disabled={!canRedo} onClick={redo}>↷</button>
            <span className={`save-state ${saveState}`}>{SAVE_LABEL[saveState]}</span>
          </>
        )}
        <div className="grow" />
        {doc?.media && (
          <span className="muted small media-info">
            {doc.media.file_name} · {doc.media.width}×{doc.media.height} · {doc.media.fps} fps · {fmtBytes(doc.media.size_bytes)}
          </span>
        )}
        {doc?.media && (
          <>
            <button className="btn accent" disabled={isRunning("autoedit")} onClick={() => { setTab("autoedit"); runAutoEdit(); }}>
              ✨ Auto-editar
            </button>
            <button className="btn primary" onClick={() => setTab("export")}>⇩ Exportar</button>
          </>
        )}
      </header>

      {systemError && <div className="banner error">{systemError}</div>}
      {system && !system.ffmpeg.ok && <div className="banner error">FFmpeg no está instalado o no se encuentra en el PATH.</div>}
      {notice && <div className="banner warn" onClick={() => setNotice(null)}>{notice} <small>(clic para cerrar)</small></div>}

      {showProjects && <ProjectsPanel currentId={projectId} onOpen={setProjectId} refreshKey={listKey} />}

      <main className="workspace">
        {!project && (
          <div className="empty-state">
            <h1>Smart Video Editor</h1>
            <p className="muted">Crea o abre un proyecto en el panel izquierdo para empezar.</p>
          </div>
        )}
        {project && doc?.media && project.media_available === false && (
          <RelinkPanel project={project} onDone={() => { reload(); refreshJobs(); }} />
        )}
        {project && !doc?.media && <ImportDropzone projectId={project.id} onImported={() => { reload(); refreshJobs(); }} />}
        {project && doc?.media && project.media_available !== false && (
          <>
            <div className="viewer">
              <Monitor projectId={project.id} doc={doc} videoRef={videoRef} applyCuts={applyCuts}
                onTime={setCurrentTime} onPlayingChange={setPlaying} currentTime={currentTime} />
              <Transport doc={doc} videoRef={videoRef} currentTime={currentTime} playing={playing}
                applyCuts={applyCuts} setApplyCuts={setApplyCuts} />
            </div>
            <aside className="inspector">
              <nav className="tabs">
                {TABS.map(([k, l]) => (
                  <button key={k} className={tab === k ? "active" : ""} onClick={() => setTab(k)}>{l}</button>
                ))}
              </nav>
              {tab === "autoedit" && <AutoEditPanel doc={doc} updateDoc={updateDoc} runAutoEdit={runAutoEdit}
                running={isRunning("autoedit")} onSeek={seek} selectedCut={selectedCut} setSelectedCut={setSelectedCut} />}
              {tab === "subtitles" && <SubtitlesPanel projectId={project.id} doc={doc} updateDoc={updateDoc}
                runTranscribe={runTranscribe} running={isRunning("transcribe")} models={system?.whisper_models ?? ["base"]}
                defaultModel={system?.default_whisper_model ?? "base"} currentTime={currentTime} onSeek={seek}
                selectedCaption={selectedCaption} setSelectedCaption={setSelectedCaption} />}
              {tab === "style" && <StylePanel doc={doc} updateDoc={updateDoc} fonts={fonts} />}
              {tab === "format" && <FormatPanel doc={doc} updateDoc={updateDoc} runFaceTrack={runFaceTrack}
                trackRunning={isRunning("facetrack")} />}
              {tab === "transitions" && <TransitionsPanel doc={doc} updateDoc={updateDoc} selectedCut={selectedCut}
                setSelectedCut={setSelectedCut} onSeek={seek} runScenes={runScenes} scenesRunning={isRunning("scenes")}
                preview={runPreview} previewRunning={isRunning("preview")}
                currentOut={toOutput(editSegments(doc.cuts, doc.media.duration), currentTime)} />}
              {tab === "audio" && <AudioPanel projectId={project.id} doc={doc} updateDoc={updateDoc} serverChange={serverChange} />}
              {tab === "export" && system && <ExportPanel projectId={project.id} doc={doc} updateDoc={updateDoc}
                profiles={system.profiles} runExport={runExport} running={isRunning("export")} lastExport={lastExport} />}
            </aside>
            <div className="timeline-area">
              {markIn !== null && (
                <div className="mark-bar">
                  Rango marcado desde {markIn.toFixed(2)} s{markOut !== null ? ` hasta ${markOut.toFixed(2)} s` : " (pulsa O para marcar la salida)"}
                  <button className="btn tiny accent" onClick={cutMarkedRange}>Eliminar rango (X)</button>
                  <button className="btn tiny ghost" onClick={() => { setMarkIn(null); setMarkOut(null); }}>Cancelar</button>
                </div>
              )}
              <Timeline projectId={project.id} doc={doc} currentTime={currentTime} playing={playing} onSeek={seek}
                updateCuts={updateCuts} selectedCut={selectedCut} setSelectedCut={setSelectedCut}
                selectedCaption={selectedCaption} setSelectedCaption={(id) => { setSelectedCaption(id); if (id) setTab("subtitles"); }}
                markIn={markIn} markOut={markOut} assetsVersion={assetsVersion + (doc.proxy_ready ? 1000 : 0)} />
            </div>
          </>
        )}
      </main>
      <footer className="statusbar">
        <JobBar jobs={jobs} onChange={refreshJobs} />
        {toast && <div className="toast" onClick={() => setToast(null)}>{toast}</div>}
        {previewJob && project && <PreviewModal projectId={project.id} job={previewJob} onClose={() => setPreviewJob(null)} />}
      </footer>
    </div>
  );
}
