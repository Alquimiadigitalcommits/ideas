import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { Caption, ProjectDoc } from "../api/types";
import { retimeText } from "../lib/captions";
import { fmtTime } from "../lib/format";
import { Section } from "./ui";

interface Props {
  projectId: string;
  doc: ProjectDoc;
  updateDoc: (fn: (d: ProjectDoc) => ProjectDoc) => void;
  runTranscribe: (model: string, language: string | null) => void;
  running: boolean;
  models: string[];
  defaultModel: string;
  currentTime: number;
  onSeek: (t: number) => void;
  selectedCaption: string | null;
  setSelectedCaption: (id: string | null) => void;
}

const LANGS: [string, string][] = [["es", "Español"], ["en", "Inglés"], ["pt", "Portugués"], ["fr", "Francés"], ["auto", "Detectar automáticamente"]];

export function SubtitlesPanel(p: Props) {
  const { doc } = p;
  const [model, setModel] = useState(p.defaultModel);
  const [lang, setLang] = useState("es");
  const listRef = useRef<HTMLUListElement>(null);
  const activeId = doc.captions.find((c) => p.currentTime >= c.start && p.currentTime <= c.end)?.id;

  useEffect(() => setModel(p.defaultModel), [p.defaultModel]);

  useEffect(() => {
    const id = p.selectedCaption;
    if (!id || !listRef.current) return;
    listRef.current.querySelector(`[data-id="${id}"]`)?.scrollIntoView({ block: "nearest" });
  }, [p.selectedCaption]);

  const editText = (c: Caption, text: string) =>
    p.updateDoc((d) => ({ ...d, captions: d.captions.map((x) => (x.id === c.id ? retimeText(x, text) : x)) }));
  const remove = (c: Caption) => p.updateDoc((d) => ({ ...d, captions: d.captions.filter((x) => x.id !== c.id) }));

  return (
    <div className="panel-scroll">
      <Section title="Transcripción automática">
        <div className="grid2">
          <label className="field">
            <span>Modelo Whisper</span>
            <select value={model} onChange={(e) => setModel(e.target.value)}>
              {p.models.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Idioma</span>
            <select value={lang} onChange={(e) => setLang(e.target.value)}>
              {LANGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
        </div>
        <small className="hint">tiny/base: rápidos en CPU · small/medium: más precisos y más lentos · la primera vez se descarga el modelo.</small>
        <button className="btn primary full" disabled={p.running || !doc.media?.has_audio}
          onClick={() => {
            if (doc.captions.some((c) => c.edited) && !confirm("Se reemplazarán los subtítulos actuales, incluidos los editados. ¿Continuar?")) return;
            p.runTranscribe(model, lang === "auto" ? null : lang);
          }}>
          {p.running ? "Transcribiendo…" : doc.captions.length ? "Volver a transcribir" : "🎙 Transcribir y generar subtítulos"}
        </button>
      </Section>

      <Section title={`Subtítulos (${doc.captions.length})`}
        right={doc.captions.length > 0 && <a className="btn ghost small" href={api.srtUrl(p.projectId)}>⇩ SRT</a>}>
        {doc.captions.length === 0 && <p className="muted small">Aún no hay subtítulos.</p>}
        {doc.language && <p className="muted small">Idioma detectado: {doc.language}. El SRT se descarga ya ajustado a los cortes.</p>}
        <ul className="caption-list" ref={listRef}>
          {doc.captions.map((c) => (
            <li key={c.id} data-id={c.id}
              className={(c.id === activeId ? "active " : "") + (c.id === p.selectedCaption ? "selected" : "")}>
              <button className="tc link" onClick={() => { p.setSelectedCaption(c.id); p.onSeek(c.start); }}>
                {fmtTime(c.start)}
              </button>
              <CaptionInput caption={c} onCommit={(t) => editText(c, t)} onFocus={() => p.setSelectedCaption(c.id)} />
              <button className="btn tiny ghost" title="Eliminar subtítulo" onClick={() => remove(c)}>✕</button>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}

function CaptionInput({ caption, onCommit, onFocus }: { caption: Caption; onCommit: (t: string) => void; onFocus: () => void }) {
  const [val, setVal] = useState(caption.text);
  useEffect(() => setVal(caption.text), [caption.text]);
  const commit = () => { if (val.trim() !== caption.text) onCommit(val); };
  return (
    <textarea rows={1} value={val} onFocus={onFocus} onChange={(e) => setVal(e.target.value)} onBlur={commit}
      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); (e.target as HTMLTextAreaElement).blur(); } }} />
  );
}
