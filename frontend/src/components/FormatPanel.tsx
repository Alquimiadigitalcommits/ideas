import type { Aspect, FormatSettings, ProjectDoc } from "../api/types";
import { Check, Section, Segmented, Slider } from "./ui";

interface Props {
  doc: ProjectDoc;
  updateDoc: (fn: (d: ProjectDoc) => ProjectDoc) => void;
  runFaceTrack: () => void;
  trackRunning: boolean;
}

const AspectIcon = ({ a }: { a: Aspect }) => {
  const [w, h] = a === "9:16" ? [12, 20] : a === "16:9" ? [24, 14] : [18, 18];
  return <span className="aspect-icon" style={{ width: w, height: h }} />;
};

export function FormatPanel({ doc, updateDoc, runFaceTrack, trackRunning }: Props) {
  const f = doc.format;
  const set = (patch: Partial<FormatSettings>) => updateDoc((d) => ({ ...d, format: { ...d.format, ...patch } }));
  const m = doc.media;

  return (
    <div className="panel-scroll">
      <Section title="Relación de aspecto">
        <Segmented<Aspect> value={f.aspect} onChange={(v) => set({ aspect: v })} options={[
          { value: "9:16", label: <><AspectIcon a="9:16" /> 9:16</>, title: "TikTok, Reels, Shorts" },
          { value: "16:9", label: <><AspectIcon a="16:9" /> 16:9</>, title: "YouTube" },
          { value: "1:1", label: <><AspectIcon a="1:1" /> 1:1</>, title: "Feed de Instagram" },
        ]} />
        {m && <small className="hint">Fuente: {m.width}×{m.height} · {m.fps} fps. Cambiar el formato no altera cortes ni subtítulos.</small>}
      </Section>
      <Section title="Reencuadre">
        <Segmented value={f.mode} onChange={(v) => set({ mode: v })} options={[
          { value: "crop", label: "Recortar", title: "Llena el cuadro recortando los bordes" },
          { value: "blur", label: "Fondo desenfocado", title: "Video completo sobre una versión desenfocada" },
          { value: "fit", label: "Barras negras", title: "Video completo con barras" },
        ]} />
        {f.mode === "crop" && (
          <>
            <Slider label="Posición horizontal" value={f.offset_x} min={0} max={1} step={0.01}
              onChange={(v) => set({ offset_x: v })} hint="0 = izquierda · 0.5 = centro · 1 = derecha" />
            <Slider label="Posición vertical" value={f.offset_y} min={0} max={1} step={0.01}
              onChange={(v) => set({ offset_y: v })} />
            <Slider label="Zoom" value={f.zoom} min={1} max={3} step={0.01} unit="×" onChange={(v) => set({ zoom: v })} />
            <button className="btn ghost small" onClick={() => set({ offset_x: 0.5, offset_y: 0.5, zoom: 1 })}>Centrar</button>
          </>
        )}
      </Section>
      <Section title="Seguir el rostro">
        <p className="muted small">Detecta la cara en todo el video y mueve el recorte para mantenerla en cuadro, con movimiento suave (cámara virtual).</p>
        <button className="btn full" disabled={trackRunning} onClick={runFaceTrack}>
          {trackRunning ? "Analizando…" : f.track.length ? "Volver a detectar el rostro" : "🙂 Detectar y seguir el rostro"}
        </button>
        {f.track.length > 0 && (
          <>
            <Check label={`Seguimiento activo (${f.track.length} puntos clave)`} checked={f.track_enabled}
              onChange={(v) => set({ track_enabled: v, mode: v ? "crop" : f.mode })} />
            {f.track_enabled && f.mode !== "crop" && <small className="hint error">Solo funciona en modo Recortar.</small>}
            <small className="hint">Con el seguimiento activo, la posición horizontal manual se ignora.</small>
          </>
        )}
      </Section>
      <Section title="Zoom alternado en cortes">
        <Slider label="Acercamiento" value={f.jump_zoom} min={0} max={0.3} step={0.01} unit="" digits={2}
          onChange={(v) => set({ jump_zoom: v })} hint="0 = desactivado. Cada segmento por medio se acerca este porcentaje: disimula los cortes en videos hablados (jump cut)." />
      </Section>
    </div>
  );
}
