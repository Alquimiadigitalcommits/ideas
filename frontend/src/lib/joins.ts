// Uniones, seguimiento de rostro y recorte: espejo de backend/app/engine/render.py y reframe.py.
import type { Cut, FormatSettings, ProjectDoc, Transition } from "../api/types";
import { type Interval, keepSegments } from "./timemap";

/** Segmentos conservados, divididos además en las divisiones (kind = "split"). */
export function editSegments(cuts: Cut[], duration: number): Interval[] {
  const segs = keepSegments(cuts, duration);
  const pts = cuts.filter((c) => c.kind === "split" && c.enabled).map((c) => c.start).sort((a, b) => a - b);
  if (!pts.length) return segs;
  const out: Interval[] = [];
  for (const [s, e] of segs) {
    let cur = s;
    for (const p of pts) if (p >= cur + 0.04 && p <= e - 0.04) { out.push([cur, p]); cur = p; }
    out.push([cur, e]);
  }
  return out;
}

export interface JoinInfo {
  index: number;
  out: number;          // tiempo de salida de la unión
  src: number;          // tiempo fuente (final del segmento anterior)
  gap: number;
  owner: Cut | null;    // corte o división que crea la unión
  trans: Transition | null;  // transición efectiva (null = corte seco)
  overrides: boolean;
}

export function computeJoins(doc: ProjectDoc): JoinInfo[] {
  const dur = doc.media?.duration ?? 0;
  const segs = editSegments(doc.cuts, dur);
  const out: JoinInfo[] = [];
  let acc = 0;
  for (let i = 0; i < segs.length - 1; i++) {
    acc += segs[i][1] - segs[i][0];
    const e = segs[i][1], sNext = segs[i + 1][0];
    const gap = Math.max(0, sNext - e);
    const owner = gap > 0.02
      ? doc.cuts.filter((c) => c.enabled && c.kind !== "split" && c.start < sNext && c.end > e).sort((a, b) => a.start - b.start)[0] ?? null
      : doc.cuts.find((c) => c.enabled && c.kind === "split" && Math.abs(c.start - e) < 0.05) ?? null;
    const t = owner?.transition ?? doc.transition_default;
    out.push({ index: i, out: acc, src: e, gap, owner, trans: t && t.type !== "none" ? t : null,
      overrides: !!owner?.transition });
  }
  return out;
}

export const TRANSITION_LABEL: Record<string, string> = {
  none: "Corte seco", fade: "Fundido a negro", dissolve: "Disolución", zoom: "Zoom", blur: "Desenfoque",
  slide: "Deslizamiento", flash: "Flash",
};

export const NEEDS_GAP = new Set(["dissolve", "slide"]);

const ASPECTS: Record<string, [number, number]> = { "9:16": [9, 16], "16:9": [16, 9], "1:1": [1, 1] };

/** Igual que reframe.crop_box: ancho/alto del recorte en píxeles de la fuente. */
export function cropSize(srcW: number, srcH: number, aspect: string, zoom = 1): [number, number] {
  const [aw, ah] = ASPECTS[aspect];
  const target = aw / ah;
  let cw: number, ch: number;
  if (srcW / srcH > target) { ch = srcH; cw = srcH * target; } else { cw = srcW; ch = srcW / target; }
  const z = Math.max(1, zoom);
  return [cw / z, ch / z];
}

/** Centro x normalizado de la trayectoria en el tiempo fuente t (interpolación lineal). */
export function trackCenterAt(track: [number, number, number][], t: number): number | null {
  if (!track.length) return null;
  if (t <= track[0][0]) return track[0][1];
  if (t >= track[track.length - 1][0]) return track[track.length - 1][1];
  for (let i = 1; i < track.length; i++) {
    if (track[i][0] >= t) {
      const [t0, c0] = track[i - 1], [t1, c1] = track[i];
      return c0 + ((c1 - c0) * (t - t0)) / Math.max(1e-6, t1 - t0);
    }
  }
  return null;
}

/** offset_x equivalente (0..1) para centrar el recorte en el rostro, como hace el render. */
export function trackOffsetAt(fmt: FormatSettings, srcW: number, srcH: number, t: number): number | null {
  if (!fmt.track_enabled || fmt.mode !== "crop") return null;
  const c = trackCenterAt(fmt.track, t);
  if (c === null) return null;
  const [cw] = cropSize(srcW, srcH, fmt.aspect, fmt.zoom);
  const span = srcW - cw;
  if (span <= 1) return 0.5;
  return Math.min(1, Math.max(0, (c * srcW - cw / 2) / span));
}
