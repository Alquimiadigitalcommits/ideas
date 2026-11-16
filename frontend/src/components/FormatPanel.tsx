import type { Aspect, FormatSettings, ProjectDoc } from "../api/types";
import { Section, Segmented, Slider } from "./ui";

interface Props {
  doc: ProjectDoc;
  updateDoc: (fn: (d: ProjectDoc) => ProjectDoc) => void;
}

const AspectIcon = ({ a }: { a: Aspect }) => {
  const [w, h] = a === "9:16" ? [12, 20] : a === "16:9" ? [24, 14] : [18, 18];
  return <span className="aspect-icon" style={{ width: w, height: h }} />;
};

export function FormatPanel({ doc, updateDoc }: Props) {
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
    </div>
  );
}
