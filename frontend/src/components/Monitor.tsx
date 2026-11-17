import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { Caption, ProjectDoc } from "../api/types";
import { cssScale } from "../lib/fonts";
import { ASPECT_RATIO } from "../lib/format";
import { computeJoins, editSegments, trackOffsetAt } from "../lib/joins";
import { activeCuts, cutEndAt, outputDuration, toOutput } from "../lib/timemap";

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

const dbToGain = (db: number) => Math.pow(10, db / 20);

export function Monitor({ projectId, doc, videoRef, applyCuts, onTime, onPlayingChange, currentTime }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const bgRef = useRef<HTMLVideoElement>(null);
  const musicRef = useRef<HTMLAudioElement>(null);
  const [box, setBox] = useState({ w: 0, h: 0 });
  const [unavailable, setUnavailable] = useState(false);
  const fmt = doc.format;
  const style = doc.subtitle_style;
  const dur = doc.media?.duration ?? 0;

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

  const active = useMemo(() => activeCuts(doc.cuts, dur), [doc.cuts, dur]);
  const segs = useMemo(() => editSegments(doc.cuts, dur), [doc.cuts, dur]);
  const joins = useMemo(() => computeJoins(doc), [doc]);
  const outTotal = outputDuration(segs);

  // refs para el bucle de reproducción (evita reiniciarlo en cada render)
  const live = useRef({ active, segs, applyCuts, doc, outTotal });
  live.current = { active, segs, applyCuts, doc, outTotal };

  useEffect(() => {
    let raf = 0;
    let lastEmit = 0;
    const loop = (ts: number) => {
      const v = videoRef.current;
      const L = live.current;
      if (v) {
        if (!v.paused && L.applyCuts) {
          const end = cutEndAt(L.active, v.currentTime);
          if (end !== null) v.currentTime = Math.min(end + 0.001, v.duration || end);
        }
        v.volume = Math.min(1, dbToGain(L.doc.audio.voice_gain_db));
        const bg = bgRef.current;
        if (bg) {
          if (Math.abs(bg.currentTime - v.currentTime) > 0.2) bg.currentTime = v.currentTime;
          if (v.paused !== bg.paused) (v.paused ? bg.pause() : bg.play().catch(() => {}));
        }
        syncMusic(v, L);
        if (ts - lastEmit > 40) {
          lastEmit = ts;
          onTime(v.currentTime);
        }
      }
      raf = requestAnimationFrame(loop);
    };
    const syncMusic = (v: HTMLVideoElement, L: typeof live.current) => {
      const a = musicRef.current;
      const m = L.doc.audio.music;
      if (!a || !m) return;
      const out = toOutput(L.segs, v.currentTime);
      if (v.paused || out === null) {
        if (!a.paused) a.pause();
        return;
      }
      let want = m.start_offset + out;
      if (m.loop && m.duration > 0) want %= m.duration;
      else if (want > m.duration) { a.pause(); return; }
      if (Math.abs(a.currentTime - want) > 0.25) a.currentTime = want;
      // volumen: dB + fundidos + ducking aproximado (hay una palabra transcrita en este instante)
      let g = dbToGain(m.volume_db);
      if (m.fade_in > 0) g *= Math.min(1, out / m.fade_in);
      if (m.fade_out > 0) g *= Math.min(1, Math.max(0, (L.outTotal - out) / m.fade_out));
      if (m.ducking && findCaption(L.doc.captions, v.currentTime)) g *= 1 - 0.85 * m.ducking_amount;
      a.volume = Math.max(0, Math.min(1, g));
      if (a.paused) a.play().catch(() => {});
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [videoRef, onTime]);

  const m = doc.media;
  const originalPlayable = !!m && m.video_codec === "h264" && /\.(mp4|mov)$/i.test(m.source_path);
  const src = doc.proxy_ready || originalPlayable ? api.previewUrl(projectId, doc.proxy_ready ? "proxy" : "orig") : null;
  useEffect(() => setUnavailable(!src), [src]);

  // ------- efectos de la vista previa (aproximación del render; la previsualización exacta lo renderiza)
  const outT = toOutput(segs, currentTime);
  let black = 0, white = 0, zoomFx = 0, blurFx = 0;
  if (outT !== null && applyCuts) {
    for (const j of joins) {
      if (!j.trans) continue;
      const half = j.trans.duration / 2;
      const d = Math.abs(outT - j.out);
      if (d >= half) continue;
      const b = 1 - d / half, k = j.trans.intensity;
      if (j.trans.type === "fade") black = Math.max(black, k * b);
      else if (j.trans.type === "flash") white = Math.max(white, k * b);
      else if (j.trans.type === "zoom") zoomFx = Math.max(zoomFx, 0.4 * k * b);
      else if (j.trans.type === "blur") blurFx = Math.max(blurFx, k * b);
      else if (j.gap > 0) black = Math.max(black, 0.25 * b);   // disolución / deslizamiento: aprox.
    }
    const a = doc.audio;
    if (a.fade_in > 0 && outT < a.fade_in) black = Math.max(black, 1 - outT / a.fade_in);
    if (a.fade_out > 0 && outTotal - outT < a.fade_out) black = Math.max(black, 1 - (outTotal - outT) / a.fade_out);
  }
  let segIdx = -1;
  for (let i = 0; i < segs.length; i++) if (currentTime >= segs[i][0] && currentTime <= segs[i][1]) { segIdx = i; break; }
  const jump = fmt.jump_zoom > 0 && segIdx % 2 === 1 ? fmt.jump_zoom : 0;
  const scale = 1 + jump + zoomFx;

  const k = Math.min(box.w, box.h) / 1080;
  // libass dimensiona con winAscent+winDescent de cada fuente y CSS con el em: el factor se mide por fuente
  const ASS_TO_CSS = cssScale(style.font_family);
  const cap = findCaption(doc.captions, currentTime);
  const wordIdx = cap ? cap.words.findIndex((w, i) => currentTime >= w.start &&
    (i === cap.words.length - 1 || currentTime < cap.words[i + 1].start)) : -1;
  const ox = m ? trackOffsetAt(fmt, m.width, m.height, currentTime) ?? fmt.offset_x : fmt.offset_x;
  const pos = `${ox * 100}% ${fmt.offset_y * 100}%`;
  const fgStyle: React.CSSProperties = fmt.mode === "crop"
    ? { objectFit: "cover", objectPosition: pos, transform: `scale(${Math.max(1, fmt.zoom)})`, transformOrigin: pos }
    : { objectFit: "contain" };
  const tx = (t: string) => (style.uppercase ? t.toUpperCase() : t);
  const anim = style.animation;
  const perWord = cap && cap.words.length > 0 && (style.highlight_words || anim === "typewriter");

  return (
    <div className="monitor" ref={wrapRef}>
      <div className="frame" style={{ width: box.w, height: box.h, background: fmt.mode === "fit" ? "#000" : "#111" }}>
        <div className="fx-layer" style={{ transform: scale !== 1 ? `scale(${scale})` : undefined,
          filter: blurFx > 0 ? `blur(${(blurFx * 22 * box.h) / 1080}px)` : undefined }}>
          {fmt.mode === "blur" && !unavailable && src && (
            <video ref={bgRef} className="bg-video" src={src} muted playsInline preload="auto" />
          )}
          {!unavailable && src ? (
            <video ref={videoRef} className="fg-video" src={src} style={fgStyle} playsInline preload="auto"
              onError={() => setUnavailable(true)} onPlay={() => onPlayingChange(true)} onPause={() => onPlayingChange(false)} />
          ) : (
            <div className="monitor-wait"><div className="spinner" />Generando previsualización…</div>
          )}
        </div>
        {(black > 0 || white > 0) && (
          <div className="fx-dip" style={{ background: white > black ? "#fff" : "#000", opacity: Math.max(black, white) }} />
        )}
        {doc.audio.music && <audio ref={musicRef} src={api.musicUrl(projectId, doc.audio.music.path)} preload="auto" />}
        {cap && (
          <div key={`${cap.id}-${anim}`}
            className={`sub-overlay anim-${anim === "pop" && style.highlight_words ? "none" : anim}`}
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
            {perWord
              ? cap.words.map((w, i) => {
                  const isActive = i === wordIdx && style.highlight_words;
                  const hidden = anim === "typewriter" && (wordIdx === -1 || i > wordIdx);
                  // el espacio va fuera del <span>: dentro de un inline-block (animación pop) se descartaría
                  return (
                    <Fragment key={i}>
                      <span key={isActive ? `a${i}` : `w${i}`}
                        className={isActive && anim === "pop" ? "word-pop" : undefined}
                        style={{ color: isActive ? style.highlight_color : undefined, visibility: hidden ? "hidden" : undefined }}>
                        {tx(w.text)}
                      </span>
                      {i < cap.words.length - 1 ? " " : ""}
                    </Fragment>
                  );
                })
              : tx(cap.text)}
          </div>
        )}
      </div>
    </div>
  );
}
