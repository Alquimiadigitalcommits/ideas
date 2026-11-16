import { describe, expect, it } from "vitest";
import type { Cut } from "../api/types";
import { activeCuts, cutEndAt, keepSegments, outputDuration, toOutput } from "./timemap";
import { buildCaptions, retimeText } from "./captions";

const c = (start: number, end: number, enabled = true): Cut =>
  ({ id: `${start}`, start, end, enabled, kind: "silence", reason: "" });

describe("timemap (mismos casos que backend/tests/test_timeline.py)", () => {
  it("keepSegments", () => {
    expect(keepSegments([c(1, 2), c(4, 5), c(6, 7, false)], 10)).toEqual([[0, 1], [2, 4], [5, 10]]);
    expect(keepSegments([c(0, 1), c(0.5, 2), c(9, 12)], 10)).toEqual([[2, 9]]);
  });
  it("toOutput", () => {
    const segs = keepSegments([c(1, 2), c(4, 5)], 10);
    expect(outputDuration(segs)).toBe(8);
    expect(toOutput(segs, 0.5)).toBe(0.5);
    expect(toOutput(segs, 1.5)).toBeNull();
    expect(toOutput(segs, 3)).toBeCloseTo(2);
  });
  it("cutEndAt", () => {
    const a = activeCuts([c(1, 2)], 10);
    expect(cutEndAt(a, 1.5)).toBe(2);
    expect(cutEndAt(a, 2.5)).toBeNull();
  });
});

describe("captions", () => {
  const W = [
    { start: 0, end: 0.4, text: "Hola" }, { start: 0.4, end: 0.5, text: "a" }, { start: 0.5, end: 1, text: "todos." },
    { start: 3, end: 3.3, text: "Hoy" }, { start: 3.3, end: 3.9, text: "probamos" }, { start: 3.9, end: 4, text: "el" },
    { start: 4, end: 4.5, text: "editor" }, { start: 4.5, end: 5, text: "nuevo" },
  ];
  it("buildCaptions", () => {
    expect(buildCaptions(W, 3, 40).map((x) => x.text)).toEqual(["Hola a todos.", "Hoy probamos el", "editor nuevo"]);
  });
  it("retimeText", () => {
    const cap = buildCaptions(W.slice(0, 3), 5, 40)[0];
    const same = retimeText(cap, "Hola a todas.");
    expect(same.words.map((w) => w.start)).toEqual([0, 0.4, 0.5]);
    const diff = retimeText(cap, "Buenas tardes");
    expect(diff.words.length).toBe(2);
    expect(diff.words[1].end).toBeCloseTo(1, 2);
  });
});
