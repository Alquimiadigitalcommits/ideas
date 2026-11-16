// Copia de las funciones de edición de backend/app/engine/subtitles.py.
import type { Caption, Word } from "../api/types";

const PUNCT_BREAK = [".", "?", "!", "…", ",", ";", ":"];

export function uid(): string {
  return Math.random().toString(16).slice(2, 10);
}

export function retimeText(c: Caption, newText: string): Caption {
  const tokens = newText.split(/\s+/).filter(Boolean);
  const base: Caption = { ...c, text: tokens.join(" "), edited: true };
  if (!tokens.length) return { ...base, words: [] };
  if (tokens.length === c.words.length) {
    return { ...base, words: c.words.map((w, i) => ({ ...w, text: tokens[i] })) };
  }
  const total = tokens.reduce((a, t) => a + t.length, 0);
  const span = c.end - c.start;
  let t = c.start;
  const words: Word[] = tokens.map((tok) => {
    const d = (span * tok.length) / total;
    const w = { start: round3(t), end: round3(t + d), text: tok };
    t += d;
    return w;
  });
  return { ...base, words };
}

export function buildCaptions(words: Word[], maxWords: number, maxChars: number,
  maxGap = 0.7, maxDuration = 4): Caption[] {
  const caps: Caption[] = [];
  let cur: Word[] = [];
  const flush = () => {
    if (!cur.length) return;
    caps.push({ id: uid(), start: cur[0].start, end: cur[cur.length - 1].end,
      text: cur.map((w) => w.text).join(" "), words: cur, edited: false });
    cur = [];
  };
  for (const w of words) {
    if (cur.length) {
      const last = cur[cur.length - 1];
      const len = cur.map((x) => x.text).join(" ").length + 1 + w.text.length;
      if (cur.length >= maxWords || len > maxChars || w.start - last.end > maxGap ||
          w.end - cur[0].start > maxDuration || PUNCT_BREAK.some((p) => last.text.endsWith(p))) flush();
    }
    cur.push(w);
  }
  flush();
  return caps;
}

export function regroup(caps: Caption[], maxWords: number, maxChars: number): Caption[] {
  return buildCaptions(caps.flatMap((c) => c.words), maxWords, maxChars);
}

function round3(x: number) {
  return Math.round(x * 1000) / 1000;
}
