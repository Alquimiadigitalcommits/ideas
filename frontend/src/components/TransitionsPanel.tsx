import { useMemo, useState } from "react";
import type { Cut, ProjectDoc, Transition, TransitionType } from "../api/types";
import { uid } from "../lib/captions";
import { fmtTime } from "../lib/format";
import { computeJoins, NEEDS_GAP, TRANSITION_LABEL } from "../lib/joins";
import { Section, Segmented, Slider } from "./ui";

interface Props {
  doc: ProjectDoc;
  updateDoc: (fn: (d: ProjectDoc) => ProjectDoc) => void;
  selectedCut: string | null;
  setSelectedCut: (id: string | null) => void;
  onSeek: (t: number) => void;
  runScenes: (threshold: number) => void;
  scenesRunning: boolean;
  preview: (center: number) => void;
  previewRunning: boolean;
  currentOut: number | null;
}

const TYPES: TransitionType[] = ["none", "fade", "dissolve", "zoom", "blur", "slide", "flash"];
const HAS_INTENSITY = new Set(["fade", "flash", "zoom", "blur"]);

function TransitionEditor({ value, onChange }: { value: Transition; onChange: (t: Transition) => void }) {
  const set = (p: Partial<Transition>) => onChange({ ...value, ...p });
  return (
    <>
      <div className="trans-grid">
        {TYPES.map((t) => (
          <button key={t} className={"trans-btn" + (value.type === t ? " active" : "")} onClick={() => set({ type: t })}>
            <span className={`trans-ico t-${t}`} />{TRANSITION_LABEL[t]}
          </button>
        ))}
      </div>
      {value.type !== "none" && (
        <>
          <Slider label="Duración" value={value.duration} min={0.1} max={2} step={0.05} unit=" s"
            onChange={(v) => set({ duration: v })} hint="Mitad antes y mitad después de la unión. No cambia la duración del video." />
          {HAS_INTENSITY.has(value.type) && (
            <Slider label="Intensidad" value={value.intensity} min={0} max={1} step={0.05}
              onChange={(v) => set({ intensity: v })} />
          )}
          {value.type === "slide" && (
            <Segmented value={value.direction} onChange={(v) => set({ direction: v })} options={[
              { value: "left", label: "← Izq." }, { value: "right", label: "Der. →" },
              { value: "up", label: "↑ Arriba" }, { value: "down", label: "↓ Abajo" }]} />
          )}
        </>
      )}
    </>
  );
}

export function TransitionsPanel(p: Props) {
  const { doc } = p;
  const [threshold, setThreshold] = useState(27);
  const joins = useMemo(() => computeJoins(doc), [doc]);
  const sel = doc.cuts.find((c) => c.id === p.selectedCut) ?? null;
  const selJoin = joins.find((j) => j.owner?.id === p.selectedCut) ?? null;
  const withTrans = joins.filter((j) => j.trans).length;
  const individual = joins.filter((j) => j.overrides).length;
  const splits = doc.cuts.filter((c) => c.kind === "split");

  const setCut = (id: string, patch: Partial<Cut>) =>
    p.updateDoc((d) => ({ ...d, cuts: d.cuts.map((c) => (c.id === id ? { ...c, ...patch } : c)) }));
  const setDefault = (t: Transition) => p.updateDoc((d) => ({ ...d, transition_default: t }));

  const splitsAtScenes = () => p.updateDoc((d) => {
    const near = (t: number) => d.cuts.some((c) => t >= c.start - 0.1 && t <= c.end + 0.1);
    const add: Cut[] = d.scenes.filter((t) => !near(t)).map((t) => ({
      id: uid(), start: t, end: t, kind: "split", enabled: true, reason: "Cambio de escena" }));
    return { ...d, cuts: [...d.cuts, ...add].sort((a, b) => a.start - b.start) };
  });

  return (
    <div className="panel-scroll">
      <Section title="Transición para todas las uniones">
        <TransitionEditor value={doc.transition_default} onChange={setDefault} />
        <p className="muted small">{joins.length} uniones · {withTrans} con transición · {individual} con ajuste individual</p>
        {individual > 0 && (
          <button className="btn ghost small" onClick={() => p.updateDoc((d) => ({ ...d, cuts: d.cuts.map((c) => ({ ...c, transition: null })) }))}>
            Aplicar a todas (quitar ajustes individuales)
          </button>
        )}
        {NEEDS_GAP.has(doc.transition_default.type) && splits.length > 0 && (
          <small className="hint">Disolución y deslizamiento necesitan material eliminado a ambos lados: en las divisiones se omiten.</small>
        )}
      </Section>

      <Section title="Unión seleccionada">
        {!sel && <p className="muted small">Haz clic en un ◆ de la línea de tiempo o en un corte.</p>}
        {sel && (
          <>
            <p className="small">
              {sel.kind === "split" ? "División" : "Corte"} en <button className="link tc" onClick={() => p.onSeek(sel.start)}>{fmtTime(sel.start)}</button>
              {!selJoin && <span className="muted"> · no genera unión (está al inicio/final o desactivado)</span>}
            </p>
            {selJoin && (
              <>
                <label className="check">
                  <input type="checkbox" checked={!sel.transition}
                    onChange={(e) => setCut(sel.id, { transition: e.target.checked ? null : { ...doc.transition_default } })} />
                  <span>Usar la transición general</span>
                </label>
                {sel.transition && <TransitionEditor value={sel.transition} onChange={(t) => setCut(sel.id, { transition: t })} />}
                {selJoin.trans && NEEDS_GAP.has(selJoin.trans.type) && selJoin.gap === 0 && (
                  <small className="hint error">En una división no hay material para {TRANSITION_LABEL[selJoin.trans.type].toLowerCase()}: se omitirá.</small>
                )}
                <button className="btn full" disabled={p.previewRunning} onClick={() => p.preview(selJoin.out)}>
                  {p.previewRunning ? "Renderizando…" : "▶ Previsualización exacta de esta unión"}
                </button>
              </>
            )}
            {sel.kind === "split" && (
              <button className="btn ghost small" onClick={() => { p.updateDoc((d) => ({ ...d, cuts: d.cuts.filter((c) => c.id !== sel.id) })); p.setSelectedCut(null); }}>
                Eliminar división
              </button>
            )}
          </>
        )}
      </Section>

      <Section title="Cambios de escena">
        <Slider label="Sensibilidad (umbral)" value={threshold} min={10} max={50} step={1} digits={0}
          onChange={setThreshold} hint="Más bajo detecta cambios más sutiles." />
        <button className="btn full" disabled={p.scenesRunning} onClick={() => p.runScenes(threshold)}>
          {p.scenesRunning ? "Analizando…" : "🎬 Detectar cambios de escena"}
        </button>
        {doc.scenes.length > 0 && (
          <>
            <p className="muted small">{doc.scenes.length} cambios detectados (líneas punteadas amarillas).</p>
            <div className="row gap-s">
              <button className="btn small" onClick={splitsAtScenes}>Crear divisiones en cada escena</button>
              {splits.length > 0 && (
                <button className="btn ghost small" onClick={() => p.updateDoc((d) => ({ ...d, cuts: d.cuts.filter((c) => c.kind !== "split") }))}>
                  Quitar {splits.length} divisiones
                </button>
              )}
            </div>
            <small className="hint">Las divisiones no quitan material: sirven para poner fundido, flash, zoom o desenfoque en cada escena.</small>
          </>
        )}
      </Section>

      <Section title="Previsualización exacta">
        <p className="muted small">La vista previa en vivo aproxima las transiciones. Esto renderiza con FFmpeg 3 s del resultado final (540p) alrededor del cabezal.</p>
        <button className="btn full" disabled={p.previewRunning || p.currentOut === null} onClick={() => p.currentOut !== null && p.preview(p.currentOut)}>
          {p.currentOut === null ? "El cabezal está dentro de un corte" : p.previewRunning ? "Renderizando…" : "▶ Renderizar 3 s aquí"}
        </button>
      </Section>
    </div>
  );
}
