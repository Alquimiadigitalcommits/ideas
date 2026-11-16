import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { Caption, ProjectDoc } from "../api/types";
import { ASPECT_RATIO } from "../lib/format";
import { activeCuts, cutEndAt } from "../lib/timemap";

interface Props {
  projectId: string;
  doc: ProjectDoc;
  videoRef: React.RefObject<HTMLVideoElement>;
  applyCuts: boolean;
  onTime: (t: number) => void;
  onPlayingChange: (p: boolean) => void;
  currentTime: number;
}

function findCaption(caps: Caption[], t: number): Caption | null {
  let lo = 0, hi = caps.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const c = caps[mid];
    if (t < c.start) hi = mid - 1;
    else if (t > c.end) lo = mid + 1;
    else return c;
  }
  return null;
}

export function Monitor({ projectId, doc, videoRef, applyCuts, onTime, onPlayingChange, currentTime }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const bgRef = useRef<HTMLVideoElement>(null);
  const [box, setBox] = useState({ w: 0, h: 0 });
  const [unavailable, setUnavailable] = useState(false);
  const fmt = doc.format;
  const style = doc.subtitle_style;

  // tamaño del cuadro según el formato
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      const r = ASPECT_RATIO[fmt.aspect];
      const W = el.clientWidth - 24, H = el.clientHeight - 24;
      const w = Math.min(W, H * r);
      setBox({ w: Math.max(0, w), h: Math.max(0, w / r) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [fmt.aspect]);

  const active = useMemo(() => activeCuts(doc.cuts, doc.media?.duration ?? 0), [doc.cuts, doc.media?.duration]);
  const activeRef = useRef(active);
  activeRef.current = active;
  const applyRef = useRef(applyCuts);
  applyRef.current = applyCuts;

  // bucle de reproducción: salto de cortes + sincronía del fondo desenfocado
  useEffect(() => {
    let raf = 0;
    let lastEmit = 0;
    const loop = (ts: number) => {
      const v = videoRef.current;
      if (v) {
        if (!v.paused && applyRef.current) {
          const end = cutEndAt(activeRef.current, v.currentTime);
          if (end !== null) v.currentTime = Math.min(end + 0.001, v.duration || end);
        }
        const bg = bgRef.current;
        if (bg) {
          if (Math.abs(bg.currentTime - v.currentTime) > 0.2) bg.currentTime = v.currentTime;
          if (v.paused !== bg.paused) (v.paused ? bg.pause() : bg.play().catch(() => {}));
        }
        if (ts - lastEmit > 40) {
          lastEmit = ts;
          onTime(v.currentTime);
        }
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [videoRef, onTime]);

  // Mientras se genera el proxy se usa el original solo si el navegador puede reproducirlo (H.264 en MP4/MOV)
  const m = doc.media;
  const originalPlayable = !!m && m.video_codec === "h264" && /\.(mp4|mov)$/i.test(m.source_path);
  const src = doc.proxy_ready || originalPlayable ? api.previewUrl(projectId, doc.proxy_ready ? "proxy" : "orig") : null;
  useEffect(() => setUnavailable(!src), [src]);

  const k = Math.min(box.w, box.h) / 1080;
  // libass usa el tamaño como altura total de línea (ascendente+descendente ≈ 1.21 em en Inter/DejaVu);
  // CSS lo usa como em. Este factor iguala la vista previa con el render final.
  const ASS_TO_CSS = 0.82;
  const cap = findCaption(doc.captions, currentTime);
  const wordIdx = cap ? cap.words.findIndex((w, i) => currentTime >= w.start &&
    (i === cap.words.length - 1 || currentTime < cap.words[i + 1].start)) : -1;
  const pos = `${fmt.offset_x * 100}% ${fmt.offset_y * 100}%`;
  const fgStyle: React.CSSProperties = fmt.mode === "crop"
    ? { objectFit: "cover", objectPosition: pos, transform: `scale(${Math.max(1, fmt.zoom)})`, transformOrigin: pos }
    : { objectFit: "contain" };
  const tx = (t: string) => (style.uppercase ? t.toUpperCase() : t);

  return (
    <div className="monitor" ref={wrapRef}>
      <div className="frame" style={{ width: box.w, height: box.h, background: fmt.mode === "fit" ? "#000" : "#111" }}>
        {fmt.mode === "blur" && !unavailable && src && (
          <video ref={bgRef} className="bg-video" src={src} muted playsInline preload="auto" />
        )}
        {!unavailable && src ? (
          <video
            ref={videoRef}
            className="fg-video"
            src={src}
            style={fgStyle}
            playsInline
            preload="auto"
            onError={() => setUnavailable(true)}
            onPlay={() => onPlayingChange(true)}
            onPause={() => onPlayingChange(false)}
          />
        ) : (
          <div className="monitor-wait"><div className="spinner" />Generando previsualización…</div>
        )}
        {cap && (
          <div
            className="sub-overlay"
            style={{
              top: style.position_y * box.h,
              fontFamily: `"${style.font_family}", sans-serif`,
              fontSize: Math.max(6, style.font_size * k * ASS_TO_CSS),
              fontWeight: style.bold ? 800 : 500,
              color: style.primary_color,
              WebkitTextStroke: `${style.outline_width * k * 2}px ${style.outline_color}`,
              filter: style.shadow > 0
                ? `drop-shadow(${style.shadow * k}px ${style.shadow * k}px 0 ${style.shadow_color}99)` : undefined,
            }}
          >
            {cap.words.length && style.highlight_words
              ? cap.words.map((w, i) => (
                  <span key={i} style={i === wordIdx ? { color: style.highlight_color } : undefined}>
                    {tx(w.text)}{i < cap.words.length - 1 ? " " : ""}
                  </span>
                ))
              : tx(cap.text)}
          </div>
        )}
      </div>
    </div>
  );
}
