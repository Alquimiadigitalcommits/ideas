import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { Job } from "../api/types";

const ACTIVE = new Set(["queued", "running"]);

/** Sigue los jobs del proyecto. Llama onFinished cuando uno pasa de activo a terminado. */
export function useJobs(projectId: string | null, onFinished: (j: Job) => void) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const prev = useRef<Map<string, string>>(new Map());
  const cb = useRef(onFinished);
  cb.current = onFinished;
  const [tick, setTick] = useState(0);

  const refresh = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    prev.current = new Map();
    setJobs([]);
  }, [projectId]);

  useEffect(() => {
    if (!projectId) return;
    let stop = false;
    let handle = 0;
    const poll = async () => {
      try {
        const list = await api.jobs(projectId);
        if (stop) return;
        for (const j of list) {
          const before = prev.current.get(j.id);
          if (before && ACTIVE.has(before) && !ACTIVE.has(j.status)) cb.current(j);
          prev.current.set(j.id, j.status);
        }
        setJobs(list);
        const anyActive = list.some((j) => ACTIVE.has(j.status));
        handle = window.setTimeout(poll, anyActive ? 500 : 3000);
      } catch {
        handle = window.setTimeout(poll, 3000);
      }
    };
    poll();
    return () => {
      stop = true;
      window.clearTimeout(handle);
    };
  }, [projectId, tick]);

  const active = jobs.filter((j) => ACTIVE.has(j.status));
  const isRunning = (kind: string) => active.some((j) => j.kind === kind);
  return { jobs, active, isRunning, refresh };
}
