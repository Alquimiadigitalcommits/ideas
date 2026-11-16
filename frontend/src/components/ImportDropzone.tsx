import { useRef, useState } from "react";
import { api } from "../api/client";

interface Props {
  projectId: string;
  onImported: () => void;
}

const OK = [".mp4", ".mov", ".mkv"];

export function ImportDropzone({ projectId, onImported }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [upload, setUpload] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [path, setPath] = useState("");

  const send = async (file: File) => {
    setError(null);
    if (!OK.some((e) => file.name.toLowerCase().endsWith(e))) return setError("Formato no soportado. Usa MP4, MOV o MKV.");
    try {
      setUpload(0);
      await api.importFile(projectId, file, setUpload);
      onImported();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUpload(null);
    }
  };

  const byPath = async () => {
    setError(null);
    try {
      await api.importPath(projectId, path.trim());
      onImported();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className={"dropzone" + (over ? " over" : "")}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f) send(f); }}>
      <div className="dz-icon">⬆</div>
      <h2>Importa un video</h2>
      <p className="muted">Arrastra un archivo MP4, MOV o MKV aquí</p>
      <button className="btn primary" onClick={() => input.current?.click()} disabled={upload !== null}>Elegir archivo</button>
      <input ref={input} type="file" accept=".mp4,.mov,.mkv,video/mp4,video/quicktime,video/x-matroska" hidden
        onChange={(e) => { const f = e.target.files?.[0]; if (f) send(f); e.target.value = ""; }} />
      {upload !== null && (
        <div className="upload-progress"><div style={{ width: `${upload * 100}%` }} /><span>Copiando al proyecto… {Math.round(upload * 100)}%</span></div>
      )}
      <details className="dz-path">
        <summary>Archivos muy grandes: usar desde su ubicación sin copiar</summary>
        <div className="row gap-s">
          <input type="text" placeholder="/ruta/al/video.mp4" value={path} onChange={(e) => setPath(e.target.value)} />
          <button className="btn" disabled={!path.trim()} onClick={byPath}>Importar</button>
        </div>
        <small className="muted">El original se abre solo en lectura; nunca se modifica.</small>
      </details>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
