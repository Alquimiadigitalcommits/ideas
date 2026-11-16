// Copia de backend/app/engine/timeline.py: misma lógica para preview y export.
import type { Cut } from "../api/types";

export type Interval = [number, number];

export function mergeIntervals(iv: Interval[]): Interval[] {
  const sorted = iv.map(([a, b]) => [Math.min(a, b), Math.max(a, b)] as Interval).sort((x, y) => x[0] - y[0]);
  const out: Interval[] = [];
  for (const [s, e] of sorted) {
    if (out.length && s <= out[out.length - 1][1]) out[out.length - 1][1] = Math.max(out[out.length - 1][1], e);
    else out.push([s, e]);
  }
  return out;
}

export function activeCuts(cuts: Cut[], duration: number): Interval[] {
  return mergeIntervals(
    cuts
      .filter((c) => c.enabled)
      .map((c) => [Math.max(0, c.start), Math.min(duration, c.end)] as Interval)
      .filter(([s, e]) => e - s > 1e-6),
  );
}

export function keepSegments(cuts: Cut[], duration: number): Interval[] {
  const segs: Interval[] = [];
  let cursor = 0;
  for (const [s, e] of activeCuts(cuts, duration)) {
    if (s > cursor) segs.push([cursor, s]);
    cursor = Math.max(cursor, e);
  }
  if (cursor < duration) segs.push([cursor, duration]);
  return segs;
}

export function outputDuration(segs: Interval[]): number {
  return segs.reduce((a, [s, e]) => a + (e - s), 0);
}

/** Tiempo de salida para un tiempo de la fuente (null si cae en un corte). */
export function toOutput(segs: Interval[], t: number): number | null {
  let acc = 0;
  for (const [s, e] of segs) {
    if (t < s) return null;
    if (t <= e) return acc + (t - s);
    acc += e - s;
  }
  return null;
}

/** Si `t` está dentro de un corte activo, devuelve el final de ese corte. */
export function cutEndAt(active: Interval[], t: number): number | null {
  for (const [s, e] of active) {
    if (t >= s && t < e - 0.01) return e;
    if (s > t) break;
  }
  return null;
}
