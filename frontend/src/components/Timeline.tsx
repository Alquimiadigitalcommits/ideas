import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { Caption, Cut, ProjectDoc } from "../api/types";
import { fmtTime } from "../lib/format";
import { computeJoins, TRANSITION_LABEL } from "../lib/joins";

interface Props {
  projectId: string;
  doc: ProjectDoc;
  currentTime: number;
  playing: boolean;
  onSeek: (t: number) => void;
  updateCuts: (fn: (cuts: Cut[]) => Cut[]) => void;
  selectedCut: string | null;
  setSelectedCut: (id: string | null) => void;
  selectedCaption: string | null;
  setSelectedCaption: (id: string | null) => void;
  markIn: number | null;
  markOut: number | null;
  assetsVersion: number;
}

const HEADER_W = 64;
const RULER_H = 24;
const V_H = 56;
const A_H = 56;
const S_H = 34;

type Drag = { id: string; edge: "start" | "end"; } | null;

export function Timeline(p: Props) {
  const { doc, projectId } = p;
  const dur = doc.media?.duration ?? 0;
  const scrollRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [vw, setVw] = useState(800);
  const [scrollLeft, setScrollLeft] = useState(0);
  const [zoom, setZoom] = useState(0); // 0 = ajustar a la ventana
  const [wave, setWave] = useState<{ pps: number; peaks: number[] } | null>(null);
  const [thumbs, setThumbs] = useState<{ count: number; interval: number; tile_width: number; tile_height: number } | null>(null);
  const [drag, setDrag] = useState<Drag>(null);
  const [snap, setSnap] = useState(true);
  const joins = useMemo(() => computeJoins(doc), [doc]);
  // puntos de imán: bordes de palabras, cambios de escena y bordes de otros cortes
  const snapPoints = useMemo(() => {
    const pts: number[] = [...doc.scenes];
    for (const c of doc.captions) for (const w of c.words) pts.push(w.start, w.end);
    for (const c of doc.cuts) pts.push(c.start, c.end);
    return pts.sort((a, b) => a - b);
  }, [doc.scenes, doc.captions, doc.cuts]);

  const fitPps = dur > 0 ? Math.max(0.02, (vw - 4) / dur) : 50;
  const pps = zoom === 0 ? fitPps : Math.max(fitPps, zoom);
  const width = Math.max(vw, dur * pps);

  // recursos de previsualización (cuando el job de preparación termina)
  useEffect(() => {
    setWave(null);
    setThumbs(null);
    if (!doc.media || !doc.proxy_ready) return; // se generan en el job de preparación
    api.waveform(projectId).then(setWave).catch(() => {});
    api.thumbsMeta(projectId).then(setThumbs).catch(() => {});
  }, [projectId, doc.media?.source_path, doc.proxy_ready, p.assetsVersion]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setVw(el.clientWidth));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // seguir el cabezal durante la reproducción
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !p.playing) return;
    const x = p.currentTime * pps;
    if (x < el.scrollLeft || x > el.scrollLeft + el.clientWidth - 40) el.scrollLeft = x - 60;
  }, [p.currentTime, p.playing, pps]);

  const t0 = scrollLeft / pps;
  const t1 = (scrollLeft + vw) / pps;

  // forma de onda: canvas del tamaño de la ventana, se dibuja solo el tramo visible
  useEffect(() => {
    const c = canvasRef.current;
    if (!c) return;
    const dpr = window.devicePixelRatio || 1;
    c.width = Math.floor(vw * dpr);
    c.height = Math.floor(A_H * dpr);
    const ctx = c.getContext("2d")!;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, vw, A_H);
    if (!wave || !wave.peaks.length) return;
    const mid = A_H / 2;
    ctx.fillStyle = "#3ec6a8";
    for (let x = 0; x < vw; x++) {
      const ta = (scrollLeft + x) / pps, tb = (scrollLeft + x + 1) / pps;
      const ia = Math.floor(ta * wave.pps), ib = Math.max(ia + 1, Math.ceil(tb * wave.pps));
      let m = 0;
      for (let i = ia; i < ib && i < wave.peaks.length; i++) if (wave.peaks[i] > m) m = wave.peaks[i];
      const h = Math.max(1, m * (A_H - 8));
      ctx.fillRect(x, mid - h / 2, 1, h);
    }
  }, [wave, vw, scrollLeft, pps]);

  const xToTime = useCallback((clientX: number) => {
    const el = scrollRef.current!;
    const r = el.getBoundingClientRect();
    return Math.max(0, Math.min(dur, (clientX - r.left + el.scrollLeft) / pps));
  }, [dur, pps]);

  // arrastre de bordes de un corte
  useEffect(() => {
    if (!drag) return;
    const move = (e: PointerEvent) => {
      let t = xToTime(e.clientX);
      if (snap && !e.altKey) {
        const tol = 8 / pps;
        let best = tol;
        for (const c of [...snapPoints, p.currentTime]) {
          const d = Math.abs(c - t);
          if (d < best && !doc.cuts.some((x) => x.id === drag.id && (Math.abs(x.start - c) < 1e-6 || Math.abs(x.end - c) < 1e-6))) {
            best = d;
            t = c;
          }
        }
      }
      p.updateCuts((cuts) => cuts.map((c) => {
        if (c.id !== drag.id) return c;
        if (drag.edge === "start") return { ...c, start: Math.min(t, c.end - 0.05) };
        return { ...c, end: Math.max(t, c.start + 0.05) };
      }));
    };
    const up = () => setDrag(null);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up, { once: true });
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, [drag, xToTime, snap, snapPoints, pps]);

  const ticks = useMemo(() => {
    const steps = [0.1, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800];
    const step = steps.find((s) => s * pps >= 70) ?? 3600;
    const out: number[] = [];
    for (let t = Math.floor(t0 / step) * step; t <= t1 + step; t += step) if (t >= 0 && t <= dur) out.push(t);
    return { step, out };
  }, [t0, t1, pps, dur]);

  const visibleCuts = doc.cuts.filter((c) => c.kind !== "split" && c.end >= t0 - 1 && c.start <= t1 + 1);
  const visibleSplits = doc.cuts.filter((c) => c.kind === "split" && c.start >= t0 - 1 && c.start <= t1 + 1);
  const visibleScenes = doc.scenes.filter((t) => t >= t0 - 1 && t <= t1 + 1);
  const visibleJoins = joins.filter((j) => j.src >= t0 - 1 && j.src <= t1 + 1);
  const visibleCaps: Caption[] = doc.captions.filter((c) => c.end >= t0 - 1 && c.start <= t1 + 1);

  const thumbTiles = useMemo(() => {
    if (!thumbs) return [];
    const dispW = (V_H - 6) * thumbs.tile_width / thumbs.tile_height;
    const out: { x: number; i: number }[] = [];
    const startX = Math.floor(scrollLeft / dispW) * dispW;
    for (let x = startX; x < scrollLeft + vw && x < width; x += dispW) {
      out.push({ x, i: Math.min(thumbs.count - 1, Math.floor(x / pps / thumbs.interval)) });
    }
    return out.map((o) => ({ ...o, dispW }));
  }, [thumbs, scrollLeft, vw, pps, width]);

  const totalH = RULER_H + V_H + A_H + S_H;
  const startSeek = (e: React.PointerEvent) => {
    if ((e.target as HTMLElement).closest(".cut-region, .caption-block")) return;
    p.onSeek(xToTime(e.clientX));
    p.setSelectedCut(null);
    const move = (ev: PointerEvent) => p.onSeek(xToTime(ev.clientX));
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", () => window.removeEventListener("pointermove", move), { once: true });
  };

  return (
    <div className="timeline">
      <div className="timeline-toolbar">
        <span className="muted small">Zoom</span>
        <input type="range" min={0} max={300} step={1} value={zoom === 0 ? 0 : Math.min(300, zoom)}
          onChange={(e) => setZoom(Number(e.target.value))} />
        <button className="btn ghost small" onClick={() => setZoom(0)}>Ajustar</button>
        <button className={"btn small " + (snap ? "accent" : "ghost")} title="Imán: ajusta los bordes a palabras, escenas y cabezal (Alt lo desactiva al arrastrar)"
          onClick={() => setSnap(!snap)}>🧲 Imán</button>
        <span className="muted small">
          Doble clic en un corte = recuperar/cortar · I/O/X = cortar rango · S = dividir · ◆ = transición
        </span>
      </div>
      <div className="timeline-body">
        <div className="track-headers" style={{ width: HEADER_W }}>
          <div style={{ height: RULER_H }} />
          <div className="track-header" style={{ height: V_H }}>V1<small>video</small></div>
          <div className="track-header" style={{ height: A_H }}>A1<small>audio</small></div>
          <div className="track-header" style={{ height: S_H }}>S1<small>subs</small></div>
        </div>
        <div className="tracks-scroll" ref={scrollRef} onScroll={(e) => setScrollLeft(e.currentTarget.scrollLeft)}>
          <div className="tracks" style={{ width, height: totalH }} onPointerDown={startSeek}>
            {/* regla */}
            <div className="ruler" style={{ height: RULER_H }}>
              {ticks.out.map((t) => (
                <div key={t} className="tick" style={{ left: t * pps }}>
                  <span>{fmtTime(t, ticks.step < 1)}</span>
                </div>
              ))}
            </div>
            {/* video */}
            <div className="track video-track" style={{ top: RULER_H, height: V_H }}>
              {thumbTiles.map(({ x, i, dispW }) => (
                <div key={x} className="thumb" style={{
                  left: x, width: dispW, height: V_H - 6,
                  backgroundImage: `url(${api.thumbsUrl(projectId)}?v=${p.assetsVersion})`,
                  backgroundSize: `${thumbs!.count * dispW}px ${V_H - 6}px`,
                  backgroundPosition: `-${i * dispW}px 0`,
                }} />
              ))}
            </div>
            {/* audio */}
            <div className="track audio-track" style={{ top: RULER_H + V_H, height: A_H }}>
              <canvas ref={canvasRef} style={{ position: "absolute", left: scrollLeft, width: vw, height: A_H }} />
            </div>
            {/* subtítulos */}
            <div className="track subs-track" style={{ top: RULER_H + V_H + A_H, height: S_H }}>
              {visibleCaps.map((c) => (
                <div key={c.id}
                  className={"caption-block" + (c.id === p.selectedCaption ? " selected" : "") + (c.edited ? " edited" : "")}
                  style={{ left: c.start * pps, width: Math.max(2, (c.end - c.start) * pps) }}
                  title={c.text}
                  onPointerDown={(e) => { e.stopPropagation(); p.setSelectedCaption(c.id); p.onSeek(c.start); }}>
                  {(c.end - c.start) * pps > 24 ? c.text : ""}
                </div>
              ))}
            </div>
            {/* cortes: cubren todas las pistas */}
            {visibleCuts.map((c) => (
              <div key={c.id}
                className={`cut-region ${c.enabled ? "on" : "off"} ${c.kind}` + (c.id === p.selectedCut ? " selected" : "")}
                style={{ left: c.start * pps, width: Math.max(2, (c.end - c.start) * pps), top: RULER_H, height: V_H + A_H + S_H }}
                title={`${c.enabled ? "Eliminado" : "Recuperado"} · ${fmtTime(c.start)}–${fmtTime(c.end)} · ${c.reason || c.kind}`}
                onPointerDown={(e) => { e.stopPropagation(); p.setSelectedCut(c.id); }}
                onDoubleClick={() => p.updateCuts((cuts) => cuts.map((x) => x.id === c.id ? { ...x, enabled: !x.enabled } : x))}>
                <div className="cut-handle l" onPointerDown={(e) => { e.stopPropagation(); p.setSelectedCut(c.id); setDrag({ id: c.id, edge: "start" }); }} />
                <div className="cut-handle r" onPointerDown={(e) => { e.stopPropagation(); p.setSelectedCut(c.id); setDrag({ id: c.id, edge: "end" }); }} />
              </div>
            ))}
            {/* cambios de escena */}
            {visibleScenes.map((t) => (
              <div key={`sc${t}`} className="scene-marker" style={{ left: t * pps, height: totalH }} title={`Cambio de escena ${fmtTime(t)}`} />
            ))}
            {/* divisiones */}
            {visibleSplits.map((c) => (
              <div key={c.id} className={"split-marker" + (c.id === p.selectedCut ? " selected" : "")}
                style={{ left: c.start * pps, top: RULER_H, height: V_H + A_H + S_H }} title={`División ${fmtTime(c.start)}`}
                onPointerDown={(e) => { e.stopPropagation(); p.setSelectedCut(c.id); }} />
            ))}
            {/* uniones con transición */}
            {visibleJoins.map((j) => (
              <div key={`j${j.index}`} className={"join-marker" + (j.trans ? " has" : "") + (j.owner && j.owner.id === p.selectedCut ? " selected" : "")}
                style={{ left: j.src * pps }}
                title={`${j.trans ? TRANSITION_LABEL[j.trans.type] + " · " + j.trans.duration.toFixed(2) + " s" : "Corte seco"}${j.overrides ? " (individual)" : ""}`}
                onPointerDown={(e) => { e.stopPropagation(); if (j.owner) p.setSelectedCut(j.owner.id); p.onSeek(j.src); }}>◆</div>
            ))}
            {/* rango marcado */}
            {p.markIn !== null && (
              <div className="mark-range" style={{
                left: Math.min(p.markIn, p.markOut ?? p.markIn) * pps,
                width: Math.max(2, Math.abs((p.markOut ?? p.markIn) - p.markIn) * pps), top: RULER_H, height: totalH - RULER_H,
              }} />
            )}
            <div className="playhead" style={{ left: p.currentTime * pps, height: totalH }} />
          </div>
        </div>
      </div>
    </div>
  );
}
