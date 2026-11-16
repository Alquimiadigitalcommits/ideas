import { useMemo } from "react";
import type { AutoEditSettings, Cut, ProjectDoc } from "../api/types";
import { fmtTime } from "../lib/format";
import { keepSegments, outputDuration } from "../lib/timemap";
import { Check, Section, Slider } from "./ui";

interface Props {
  doc: ProjectDoc;
  updateDoc: (fn: (d: ProjectDoc) => ProjectDoc) => void;
  runAutoEdit: () => void;
  running: boolean;
  onSeek: (t: number) => void;
  selectedCut: string | null;
  setSelectedCut: (id: string | null) => void;
}

export function AutoEditPanel({ doc, updateDoc, runAutoEdit, running, onSeek, selectedCut, setSelectedCut }: Props) {
  const s = doc.autoedit;
  const set = (patch: Partial<AutoEditSettings>) => updateDoc((d) => ({ ...d, autoedit: { ...d.autoedit, ...patch } }));
  const setCuts = (fn: (c: Cut[]) => Cut[]) => updateDoc((d) => ({ ...d, cuts: fn(d.cuts) }));
  const dur = doc.media?.duration ?? 0;
  const outDur = useMemo(() => outputDuration(keepSegments(doc.cuts, dur)), [doc.cuts, dur]);
  const realCuts = doc.cuts.filter((c) => c.kind !== "split");   // las divisiones se gestionan en Transiciones
  const activeCount = realCuts.filter((c) => c.enabled).length;

  return (
    <div className="panel-scroll">
      <Section title="Detección de silencios">
        <Slider label="Umbral de silencio" value={s.noise_db} min={-60} max={-15} step={1} unit=" dB" digits={0}
          onChange={(v) => set({ noise_db: v })} hint="Más alto (p. ej. −25) corta también ruido de fondo; más bajo solo silencio real." />
        <Slider label="Pausa mínima a cortar" value={s.min_silence} min={0.2} max={3} step={0.05} unit=" s"
          onChange={(v) => set({ min_silence: v })} />
        <Slider label="Aire conservado" value={s.padding} min={0} max={0.6} step={0.01} unit=" s"
          onChange={(v) => set({ padding: v })} hint="Margen que se deja antes y después de cada corte." />
        <Slider label="Aire si la frase continúa" value={s.mid_sentence_padding} min={0} max={0.8} step={0.01} unit=" s"
          onChange={(v) => set({ mid_sentence_padding: v })} hint="Requiere transcripción: pausas a mitad de frase conservan más aire." />
        <Slider label="Segmento mínimo" value={s.min_keep} min={0} max={1} step={0.05} unit=" s"
          onChange={(v) => set({ min_keep: v })} hint="Sonidos sueltos más cortos que esto (clics, respiraciones) se eliminan junto con las pausas vecinas." />
        <Check label="Proteger palabras transcritas" checked={s.protect_words} onChange={(v) => set({ protect_words: v })} />
        <button className="btn primary full" disabled={running || !doc.media?.has_audio} onClick={runAutoEdit}>
          {running ? "Analizando…" : "✨ Detectar y cortar silencios"}
        </button>
        {!doc.captions.length && <small className="hint">Tip: transcribe primero para preservar frases completas.</small>}
      </Section>

      <Section title={`Cortes (${activeCount} activos de ${realCuts.length})`}
        right={realCuts.length > 0 && (
          <div className="row gap-s">
            <button className="btn ghost small" onClick={() => setCuts((c) => c.map((x) => (x.kind === "split" ? x : { ...x, enabled: false })))}>Recuperar todos</button>
            <button className="btn ghost small" onClick={() => setCuts((c) => c.map((x) => ({ ...x, enabled: true })))}>Activar todos</button>
          </div>
        )}>
        <div className="stats">
          <div><b>{fmtTime(dur)}</b><span>original</span></div>
          <div><b>{fmtTime(outDur)}</b><span>resultado</span></div>
          <div><b>−{fmtTime(dur - outDur)}</b><span>eliminado</span></div>
        </div>
        {realCuts.length === 0 && <p className="muted small">Sin cortes. Usa la detección automática o marca un rango con I / O en la línea de tiempo.</p>}
        <ul className="cut-list">
          {realCuts.map((c) => (
            <li key={c.id} className={(c.enabled ? "" : "off ") + (c.id === selectedCut ? "selected" : "")}
              onClick={() => { setSelectedCut(c.id); onSeek(Math.max(0, c.start - 0.8)); }}>
              <span className={`badge ${c.kind}`}>{c.kind === "manual" ? "manual" : "silencio"}</span>
              <span className="tc">{fmtTime(c.start)} → {fmtTime(c.end)}</span>
              <span className="muted small grow">{(c.end - c.start).toFixed(2)} s</span>
              <button className="btn tiny" onClick={(e) => { e.stopPropagation(); setCuts((all) => all.map((x) => x.id === c.id ? { ...x, enabled: !x.enabled } : x)); }}>
                {c.enabled ? "Recuperar" : "Cortar"}
              </button>
              <button className="btn tiny ghost" title="Eliminar corte" onClick={(e) => { e.stopPropagation(); setCuts((all) => all.filter((x) => x.id !== c.id)); }}>✕</button>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}
