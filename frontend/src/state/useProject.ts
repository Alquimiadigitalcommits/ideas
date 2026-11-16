import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Project, ProjectDoc } from "../api/types";

export type SaveState = "saved" | "dirty" | "saving" | "error";

const AUTOSAVE_MS = 700;

/** Proyecto abierto + autoguardado con control de revisión (409 → recarga del servidor). */
export function useProject(projectId: string | null) {
  const [project, setProject] = useState<Project | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [notice, setNotice] = useState<string | null>(null);
  const projRef = useRef<Project | null>(null);
  const dirtyRef = useRef(false);
  const timer = useRef<number | null>(null);
  const inflight = useRef<Promise<void> | null>(null);

  const apply = (p: Project | null) => {
    projRef.current = p;
    setProject(p);
  };

  const load = useCallback(async () => {
    if (!projectId) return apply(null);
    const p = await api.getProject(projectId);
    dirtyRef.current = false;
    setSaveState("saved");
    apply(p);
  }, [projectId]);

  useEffect(() => {
    apply(null);
    load().catch((e) => setNotice(String(e.message ?? e)));
  }, [load]);

  const save = useCallback(async (): Promise<void> => {
    if (inflight.current) await inflight.current;
    const p = projRef.current;
    if (!p || !dirtyRef.current) return;
    dirtyRef.current = false;
    setSaveState("saving");
    const run = (async () => {
      try {
        const saved = await api.saveProject(p.id, p.rev, p.doc, p.name);
        // Conservar cambios hechos mientras se guardaba
        const cur = projRef.current!;
        apply({ ...cur, rev: saved.rev, updated_at: saved.updated_at });
        setSaveState(dirtyRef.current ? "dirty" : "saved");
      } catch (e) {
        if (e instanceof ApiError && e.status === 409 && e.body?.project) {
          apply(e.body.project as Project);
          setNotice("El proyecto se actualizó en el motor (resultado de un proceso). Se recargó la última versión.");
          setSaveState("saved");
        } else {
          dirtyRef.current = true;
          setSaveState("error");
          setNotice(`No se pudo guardar: ${(e as Error).message}`);
        }
      }
    })();
    inflight.current = run;
    await run;
    inflight.current = null;
    if (dirtyRef.current) schedule();
  }, []);

  const schedule = useCallback(() => {
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => void save(), AUTOSAVE_MS);
  }, [save]);

  const updateDoc = useCallback((fn: (d: ProjectDoc) => ProjectDoc) => {
    const p = projRef.current;
    if (!p) return;
    apply({ ...p, doc: fn(p.doc) });
    dirtyRef.current = true;
    setSaveState("dirty");
    schedule();
  }, [schedule]);

  const rename = useCallback((name: string) => {
    const p = projRef.current;
    if (!p) return;
    apply({ ...p, name });
    dirtyRef.current = true;
    setSaveState("dirty");
    schedule();
  }, [schedule]);

  /** Guarda lo pendiente ya (antes de lanzar un proceso en el motor). */
  const flush = useCallback(async () => {
    if (timer.current) window.clearTimeout(timer.current);
    await save();
  }, [save]);

  useEffect(() => {
    const onUnload = (e: BeforeUnloadEvent) => {
      if (dirtyRef.current) {
        void save();
        e.preventDefault();
      }
    };
    window.addEventListener("beforeunload", onUnload);
    return () => window.removeEventListener("beforeunload", onUnload);
  }, [save]);

  return { project, updateDoc, rename, flush, reload: load, saveState, notice, setNotice };
}
