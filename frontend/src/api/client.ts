import type {
  AutoEditSettings, AutoRequest, BundledFont, ExportFile, ExportRequest, Job, Project, ProjectDoc, SystemInfo,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: any) {
    super(message);
  }
}

async function req<T>(method: string, url: string, body?: unknown, isForm = false): Promise<T> {
  const init: RequestInit = { method };
  if (body !== undefined) {
    if (isForm) init.body = body as FormData;
    else {
      init.body = JSON.stringify(body);
      init.headers = { "Content-Type": "application/json" };
    }
  }
  const r = await fetch(url, init);
  const text = await r.text();
  const data = text ? safeJson(text) : null;
  if (!r.ok) {
    const detail = data && typeof data === "object" && "detail" in data ? data.detail : text;
    throw new ApiError(r.status, typeof detail === "string" ? detail : JSON.stringify(detail), data);
  }
  return data as T;
}

function safeJson(t: string) {
  try {
    return JSON.parse(t);
  } catch {
    return t;
  }
}

export const api = {
  system: () => req<SystemInfo>("GET", "/api/system"),
  fonts: () => req<string[]>("GET", "/api/fonts"),
  listProjects: () => req<Project[]>("GET", "/api/projects"),
  createProject: (name: string) => req<Project>("POST", "/api/projects", { name }),
  getProject: (id: string) => req<Project>("GET", `/api/projects/${id}`),
  saveProject: (id: string, rev: number, doc: ProjectDoc, name?: string) =>
    req<Project>("PUT", `/api/projects/${id}`, { rev, doc, name }),
  deleteProject: (id: string) => req<{ ok: boolean }>("DELETE", `/api/projects/${id}`),

  importFile: (id: string, file: File, onProgress?: (f: number) => void, prepare = true) =>
    new Promise<Job | null>((resolve, reject) => {
      // XHR para poder mostrar el progreso de subida
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `/api/projects/${id}/import?prepare=${prepare}`);
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
      xhr.onload = () => {
        const data = safeJson(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) resolve(data);
        else reject(new ApiError(xhr.status, data?.detail ?? "Error al importar"));
      };
      xhr.onerror = () => reject(new ApiError(0, "No se pudo conectar con el motor local"));
      const fd = new FormData();
      fd.append("file", file);
      xhr.send(fd);
    }),
  importPath: (id: string, path: string, prepare = true) =>
    req<Job | null>("POST", `/api/projects/${id}/import-path`, { path, prepare }),
  auto: (id: string, r: AutoRequest) => req<Job>("POST", `/api/projects/${id}/auto`, r),
  prepare: (id: string) => req<Job>("POST", `/api/projects/${id}/prepare`),
  job: (jid: string) => req<Job>("GET", `/api/jobs/${jid}`),
  fontsBundled: () => req<BundledFont[]>("GET", "/api/fonts/bundled"),

  transcribe: (id: string, model: string, language: string | null) =>
    req<Job>("POST", `/api/projects/${id}/transcribe`, { model, language }),
  autoedit: (id: string, settings: AutoEditSettings) => req<Job>("POST", `/api/projects/${id}/autoedit`, settings),
  export: (id: string, r: ExportRequest) => req<Job>("POST", `/api/projects/${id}/export`, r),

  scenes: (id: string, threshold = 27) => req<Job>("POST", `/api/projects/${id}/scenes`, { threshold }),
  facetrack: (id: string) => req<Job>("POST", `/api/projects/${id}/facetrack`),
  previewClip: (id: string, center: number, span: number) =>
    req<Job>("POST", `/api/projects/${id}/preview-clip`, { center, span }),
  previewClipUrl: (id: string, name: string) => `/api/projects/${id}/previews/${encodeURIComponent(name)}`,
  uploadMusic: (id: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return req<Project>("POST", `/api/projects/${id}/music`, fd, true);
  },
  deleteMusic: (id: string) => req<Project>("DELETE", `/api/projects/${id}/music`),
  musicUrl: (id: string, v: string) => `/api/projects/${id}/media/music?v=${encodeURIComponent(v)}`,
  importProject: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return req<Project>("POST", "/api/projects/import", fd, true);
  },
  relink: (id: string, path: string, force = false) => req<Job>("POST", `/api/projects/${id}/relink`, { path, force }),

  jobs: (id: string) => req<Job[]>("GET", `/api/projects/${id}/jobs`),
  cancelJob: (jid: string) => req<{ ok: boolean }>("POST", `/api/jobs/${jid}/cancel`),
  exports: (id: string) => req<ExportFile[]>("GET", `/api/projects/${id}/exports`),

  previewUrl: (id: string, v: number | string) => `/api/projects/${id}/media/preview?v=${v}`,
  thumbsUrl: (id: string) => `/api/projects/${id}/media/thumbs.jpg`,
  thumbsMeta: (id: string) =>
    req<{ count: number; interval: number; tile_width: number; tile_height: number }>(
      "GET", `/api/projects/${id}/media/thumbs.json`),
  waveform: (id: string) => req<{ pps: number; peaks: number[] }>("GET", `/api/projects/${id}/media/waveform`),
  srtUrl: (id: string) => `/api/projects/${id}/subtitles.srt`,
  projectFileUrl: (id: string) => `/api/projects/${id}/project-file`,
  exportUrl: (id: string, name: string) => `/api/projects/${id}/exports/${encodeURIComponent(name)}`,
};
