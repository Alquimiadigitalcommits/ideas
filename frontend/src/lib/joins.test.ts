import { describe, expect, it } from "vitest";
import type { Cut, ProjectDoc } from "../api/types";
import { computeJoins, editSegments, trackOffsetAt } from "./joins";

const cut = (start: number, end: number, kind: Cut["kind"] = "manual", extra: Partial<Cut> = {}): Cut =>
  ({ id: `${kind}${start}`, start, end, kind, enabled: true, reason: "", ...extra });

describe("joins (espejo de backend/tests/test_stages.py)", () => {
  it("editSegments divide en las divisiones sin quitar material", () => {
    expect(editSegments([cut(2, 3), cut(5, 5, "split")], 10)).toEqual([[0, 2], [3, 5], [5, 10]]);
  });

  it("computeJoins: transición por defecto e individual", () => {
    const doc = {
      media: { duration: 10 } as any,
      cuts: [cut(2, 3), cut(5, 5, "split", { transition: { type: "flash", duration: 0.3, intensity: 1, direction: "left" } })],
      transition_default: { type: "fade", duration: 0.5, intensity: 1, direction: "left" },
    } as unknown as ProjectDoc;
    const j = computeJoins(doc);
    expect(j.length).toBe(2);
    expect(j[0].out).toBe(2);
    expect(j[0].gap).toBe(1);
    expect(j[0].trans?.type).toBe("fade");
    expect(j[1].out).toBe(4);
    expect(j[1].trans?.type).toBe("flash");
    expect(j[1].overrides).toBe(true);
  });

  it("trackOffsetAt centra el recorte en el rostro como el render", () => {
    const fmt = { aspect: "9:16", mode: "crop", offset_x: 0.5, offset_y: 0.5, zoom: 1, jump_zoom: 0,
      track_enabled: true, track: [[0, 0.2, 0.5], [10, 0.8, 0.5]] } as any;
    // 1920x1080 → recorte 607.5 px; centro 0.5 → offset 0.5
    expect(trackOffsetAt(fmt, 1920, 1080, 5)).toBeCloseTo(0.5, 3);
    expect(trackOffsetAt(fmt, 1920, 1080, 0)).toBeCloseTo((0.2 * 1920 - 607.5 / 2) / (1920 - 607.5), 3);
    expect(trackOffsetAt({ ...fmt, track_enabled: false }, 1920, 1080, 0)).toBeNull();
  });
});
