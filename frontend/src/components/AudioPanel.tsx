import { useRef, useState } from "react";
import { api } from "../api/client";
import type { AudioSettings, MusicTrack, ProjectDoc } from "../api/types";
import { fmtTime } from "../lib/format";
import { Check, Section, Slider } from "./ui";

interface Props {
  projectId: string;
  doc: ProjectDoc;
  updateDoc: (fn: (d: ProjectDoc) => ProjectDoc) => void;
  serverChange: (fn: () => Promise<unknown>) => Promise<void>;
}

export function AudioPanel({ projectId, doc, updateDoc, serverChange }: Props) {
  const a = doc.audio;
  const m = a.music;
  const input = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (patch: Partial<AudioSettings>) => updateDoc((d) => ({ ...d, audio: { ...d.audio, ...patch } }));
  const setM = (patch: Partial<MusicTrack>) =>
    updateDoc((d) => ({ ...d, audio: { ...d.audio, music: d.audio.music ? { ...d.audio.music, ...patch } : null } }));

  const upload = async (f: File) => {
    setError(null);
    setBusy(true);
    try { await serverChange(() => api.uploadMusic(projectId, f)); } catch (e) { setError((e as Error).message); }
    setBusy(false);
  };

  return (
    <div className="panel-scroll">
      <Section title="Voz">
        <Slider label="Volumen de la voz" value={a.voice_gain_db} min={-12} max={12} step={0.5} unit=" dB" digits={1}
          onChange={(v) => set({ voice_gain_db: v })} />
        <Check label="Quitar graves (< 80 Hz): manejo, viento, aire acondicionado" checked={a.highpass} onChange={(v) => set({ highpass: v })} />
        <Check label="Reducción de ruido" checked={a.denoise} onChange={(v) => set({ denoise: v })} />
        {a.denoise && (
          <Slider label="Fuerza" value={a.denoise_strength} min={0} max={1} step={0.05}
            onChange={(v) => set({ denoise_strength: v })} hint="El piso de ruido se mide en la pausa más larga del video. Se escucha en la exportación y en la previsualización exacta." />
        )}
      </Section>

      <Section title="Música de fondo">
        {!m && (
          <>
            <button className="btn full" disabled={busy} onClick={() => input.current?.click()}>{busy ? "Subiendo…" : "♪ Agregar música"}</button>
            <small className="hint">MP3, WAV, M4A, AAC, OGG, FLAC u OPUS. Usa música con licencia para redes.</small>
          </>
        )}
        <input ref={input} type="file" hidden accept=".mp3,.wav,.m4a,.aac,.ogg,.flac,.opus,audio/*"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
        {m && (
          <>
            <div className="music-card">
              <b>♪ {m.file_name}</b><span className="muted small">{fmtTime(m.duration, false)}</span>
              <button className="btn tiny ghost" onClick={() => input.current?.click()}>Cambiar</button>
              <button className="btn tiny ghost" onClick={() => serverChange(() => api.deleteMusic(projectId))}>Quitar</button>
            </div>
            <Slider label="Volumen" value={m.volume_db} min={-40} max={0} step={1} unit=" dB" digits={0} onChange={(v) => setM({ volume_db: v })} />
            <Slider label="Empezar la canción en" value={m.start_offset} min={0} max={Math.max(0, m.duration - 1)} step={0.5} unit=" s" digits={1}
              onChange={(v) => setM({ start_offset: v })} />
            <Check label="Repetir si el video es más largo" checked={m.loop} onChange={(v) => setM({ loop: v })} />
            <div className="grid2">
              <Slider label="Entrada" value={m.fade_in} min={0} max={5} step={0.25} unit=" s" onChange={(v) => setM({ fade_in: v })} />
              <Slider label="Salida" value={m.fade_out} min={0} max={8} step={0.25} unit=" s" onChange={(v) => setM({ fade_out: v })} />
            </div>
            <Check label="Bajar la música cuando hay voz (ducking)" checked={m.ducking} onChange={(v) => setM({ ducking: v })} />
            {m.ducking && <Slider label="Cuánto baja" value={m.ducking_amount} min={0} max={1} step={0.05} onChange={(v) => setM({ ducking_amount: v })} />}
            <small className="hint">En la vista previa el ducking se aproxima con los subtítulos; en la exportación lo hace un compresor que escucha la voz.</small>
          </>
        )}
        {error && <p className="error small">{error}</p>}
      </Section>

      <Section title="Fundidos del resultado">
        <div className="grid2">
          <Slider label="Entrada (negro)" value={a.fade_in} min={0} max={5} step={0.25} unit=" s" onChange={(v) => set({ fade_in: v })} />
          <Slider label="Salida (negro)" value={a.fade_out} min={0} max={5} step={0.25} unit=" s" onChange={(v) => set({ fade_out: v })} />
        </div>
        <small className="hint">Imagen y sonido a la vez, al inicio y al final del video exportado.</small>
      </Section>
    </div>
  );
}
