// Fuentes incluidas: se cargan desde el motor para que la vista previa use los mismos archivos que libass.
import { api } from "../api/client";

const scales = new Map<string, number>();
let loaded: Promise<void> | null = null;

/** Factor ASS → CSS de cada fuente (libass usa winAscent+winDescent; CSS usa el em). 0.82 = Inter/sistema. */
export function cssScale(family: string): number {
  return scales.get(family) ?? 0.82;
}

export function loadBundledFonts(): Promise<void> {
  if (!loaded) {
    loaded = api.fontsBundled().then(async (list) => {
      await Promise.all(list.map(async (f) => {
        scales.set(f.family, f.css_scale);
        try {
          const face = new FontFace(f.family, `url(/api/fonts/file/${encodeURIComponent(f.file)})`, { weight: String(f.weight) });
          document.fonts.add(await face.load());
        } catch { /* si una fuente no carga, la vista previa usa la de reemplazo */ }
      }));
    }).catch(() => {});
  }
  return loaded;
}
