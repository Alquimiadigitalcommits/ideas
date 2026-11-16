export function fmtTime(t: number, withMs = true): string {
  if (!isFinite(t) || t < 0) t = 0;
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const s = Math.floor(t % 60);
  const ms = Math.floor((t % 1) * 10);
  const core = `${h ? h + ":" : ""}${String(m).padStart(h ? 2 : 1, "0")}:${String(s).padStart(2, "0")}`;
  return withMs ? `${core}.${ms}` : core;
}

export function fmtBytes(b: number): string {
  if (b > 1e9) return (b / 1e9).toFixed(2) + " GB";
  if (b > 1e6) return (b / 1e6).toFixed(1) + " MB";
  return Math.round(b / 1e3) + " KB";
}

export const ASPECT_RATIO: Record<string, number> = { "9:16": 9 / 16, "16:9": 16 / 9, "1:1": 1 };
