"""Filtros de reencuadre entre formatos (9:16, 16:9, 1:1)."""
from __future__ import annotations

from ..schemas import FormatSettings

ASPECTS = {"9:16": (9, 16), "16:9": (16, 9), "1:1": (1, 1)}


def output_size(aspect: str, short_side: int = 1080) -> tuple[int, int]:
    aw, ah = ASPECTS[aspect]
    if aw >= ah:
        h = short_side
        w = round(h * aw / ah)
    else:
        w = short_side
        h = round(w * ah / aw)
    return w - w % 2, h - h % 2


def crop_box(src_w: int, src_h: int, aspect: str, offset_x: float, offset_y: float,
             zoom: float = 1.0) -> tuple[int, int, int, int]:
    """Región de la fuente (w, h, x, y) con la relación de aspecto destino."""
    aw, ah = ASPECTS[aspect]
    target = aw / ah
    if src_w / src_h > target:
        ch = src_h
        cw = src_h * target
    else:
        cw = src_w
        ch = src_w / target
    zoom = max(1.0, zoom)
    cw, ch = cw / zoom, ch / zoom
    cw, ch = int(cw) - int(cw) % 2, int(ch) - int(ch) % 2
    x = round((src_w - cw) * min(1, max(0, offset_x)))
    y = round((src_h - ch) * min(1, max(0, offset_y)))
    return cw, ch, x, y


def build_filter(inp: str, out: str, src_w: int, src_h: int, fmt: FormatSettings,
                 out_w: int, out_h: int) -> str:
    """Cadena filter_complex que lleva [inp] al tamaño de salida en [out]."""
    if fmt.mode == "crop":
        cw, ch, x, y = crop_box(src_w, src_h, fmt.aspect, fmt.offset_x, fmt.offset_y, fmt.zoom)
        return f"[{inp}]crop={cw}:{ch}:{x}:{y},scale={out_w}:{out_h}:flags=lanczos,setsar=1[{out}]"
    fit = (f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease:flags=lanczos,"
           f"scale=trunc(iw/2)*2:trunc(ih/2)*2")
    if fmt.mode == "fit":
        return (f"[{inp}]{fit},pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1[{out}]")
    # blur: fondo cubriendo el cuadro y desenfocado + video completo encima
    return (f"[{inp}]split=2[rf_bg][rf_fg];"
            f"[rf_bg]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,crop={out_w}:{out_h},"
            f"scale=iw/4:ih/4,boxblur=10:2,scale={out_w}:{out_h},eq=brightness=-0.08[rf_bgb];"
            f"[rf_fg]{fit}[rf_fgs];"
            f"[rf_bgb][rf_fgs]overlay=(W-w)/2:(H-h)/2,setsar=1[{out}]")
