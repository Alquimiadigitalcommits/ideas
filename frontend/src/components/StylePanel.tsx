import type { ProjectDoc, SubtitleStyle } from "../api/types";
import { regroup } from "../lib/captions";
import { SUBTITLE_PRESETS } from "../lib/presets";
import { Check, Color, Section, Slider } from "./ui";

interface Props {
  doc: ProjectDoc;
  updateDoc: (fn: (d: ProjectDoc) => ProjectDoc) => void;
  fonts: string[];
}

export function StylePanel({ doc, updateDoc, fonts }: Props) {
  const s = doc.subtitle_style;
  const set = (patch: Partial<SubtitleStyle>) =>
    updateDoc((d) => ({ ...d, subtitle_style: { ...d.subtitle_style, ...patch, preset: patch.preset ?? "personalizado" } }));
  const setGrouping = (patch: Partial<SubtitleStyle>) =>
    updateDoc((d) => {
      const st = { ...d.subtitle_style, ...patch };
      return { ...d, subtitle_style: st, captions: regroup(d.captions, st.max_words, st.max_chars) };
    });
  const fontList = fonts.includes(s.font_family) ? fonts : [s.font_family, ...fonts];

  return (
    <div className="panel-scroll">
      <Section title="Estilos predeterminados">
        <div className="preset-grid">
          {Object.entries(SUBTITLE_PRESETS).map(([key, { label, ...st }]) => (
            <button key={key} className={"preset" + (s.preset === key ? " active" : "")}
              onClick={() => set({ ...st, preset: key })}
              style={{ fontFamily: st.font_family, color: st.primary_color, fontWeight: st.bold ? 800 : 500,
                textShadow: `0 0 3px ${st.outline_color}, 0 0 1px ${st.outline_color}` }}>
              {st.uppercase ? label.toUpperCase() : label}
              <span style={{ color: st.highlight_color }}> ●</span>
            </button>
          ))}
        </div>
      </Section>
      <Section title="Tipografía">
        <label className="field">
          <span>Fuente</span>
          <select value={s.font_family} onChange={(e) => set({ font_family: e.target.value })}>
            {fontList.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        </label>
        <Slider label="Tamaño" value={s.font_size} min={24} max={140} step={1} digits={0} unit=" px"
          onChange={(v) => set({ font_size: v })} hint="Referido a un lado corto de 1080 px." />
        <div className="row gap">
          <Check label="Negrita" checked={s.bold} onChange={(v) => set({ bold: v })} />
          <Check label="MAYÚSCULAS" checked={s.uppercase} onChange={(v) => set({ uppercase: v })} />
        </div>
      </Section>
      <Section title="Color, contorno y sombra">
        <div className="colors">
          <Color label="Texto" value={s.primary_color} onChange={(v) => set({ primary_color: v })} />
          <Color label="Resaltado" value={s.highlight_color} onChange={(v) => set({ highlight_color: v })} />
          <Color label="Contorno" value={s.outline_color} onChange={(v) => set({ outline_color: v })} />
          <Color label="Sombra" value={s.shadow_color} onChange={(v) => set({ shadow_color: v })} />
        </div>
        <Check label="Resaltar la palabra que se está diciendo" checked={s.highlight_words} onChange={(v) => set({ highlight_words: v })} />
        <Slider label="Grosor de contorno" value={s.outline_width} min={0} max={12} step={0.5} digits={1}
          onChange={(v) => set({ outline_width: v })} />
        <Slider label="Sombra" value={s.shadow} min={0} max={12} step={0.5} digits={1} onChange={(v) => set({ shadow: v })} />
      </Section>
      <Section title="Posición y agrupación">
        <Slider label="Posición vertical" value={s.position_y} min={0.08} max={0.95} step={0.01}
          onChange={(v) => set({ position_y: v })} hint="0 = arriba, 1 = abajo. En 9:16 evita el 15 % inferior (interfaz de TikTok/Reels)." />
        <Slider label="Palabras por bloque" value={s.max_words} min={1} max={10} step={1} digits={0}
          onChange={(v) => setGrouping({ max_words: v })} />
        <Slider label="Caracteres máximos por bloque" value={s.max_chars} min={8} max={60} step={1} digits={0}
          onChange={(v) => setGrouping({ max_chars: v })} />
      </Section>
    </div>
  );
}
