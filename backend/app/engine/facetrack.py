"""Seguimiento de rostro para reencuadre automático (OpenCV, clasificador Haar incluido).

Muestrea el video ~4 veces por segundo, toma el rostro principal, y simula una cámara virtual:
zona muerta (no se mueve por oscilaciones pequeñas) + suavizado, y simplifica la trayectoria a
pocos puntos clave. Devuelve [[t, centro_x, centro_y], ...] normalizados a 0..1.
"""
from __future__ import annotations

from typing import Callable, Optional


def _rdp(points: list[list[float]], eps: float) -> list[list[float]]:
    """Ramer–Douglas–Peucker sobre (t, x): conserva solo los puntos necesarios."""
    if len(points) < 3:
        return points
    (t0, x0, _), (t1, x1, _) = points[0], points[-1]
    dmax, idx = 0.0, 0
    for i in range(1, len(points) - 1):
        t, x, _ = points[i]
        interp = x0 + (x1 - x0) * (t - t0) / max(1e-9, t1 - t0)
        d = abs(x - interp)
        if d > dmax:
            dmax, idx = d, i
    if dmax <= eps:
        return [points[0], points[-1]]
    return _rdp(points[: idx + 1], eps)[:-1] + _rdp(points[idx:], eps)


def track_faces(path: str, duration: float, *, samples_per_second: float = 4.0, deadzone: float = 0.02,
                smoothing: float = 0.45, on_progress: Optional[Callable[[float], None]] = None,
                cancel_event=None) -> dict:
    import cv2

    from .ffmpeg import OperationCanceled

    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    if cascade.empty():
        raise RuntimeError("No se pudo cargar el detector de rostros de OpenCV")
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError("OpenCV no pudo abrir el video")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(fps / samples_per_second))
    raw: list[tuple[float, Optional[float], Optional[float]]] = []
    frame_i = 0
    prev = None
    while True:
        if cancel_event is not None and cancel_event.is_set():
            cap.release()
            raise OperationCanceled()
        ok = cap.grab()
        if not ok:
            break
        if frame_i % step == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            h, w = frame.shape[:2]
            scale = 640 / w if w > 640 else 1.0
            small = cv2.resize(frame, (round(w * scale), round(h * scale))) if scale != 1 else frame
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            sh, sw = gray.shape
            mn = (max(20, sw // 32), max(20, sw // 32))
            faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=mn)
            if not len(faces):   # contraluz o poca luz: ecualización local
                faces = cascade.detectMultiScale(clahe.apply(gray), scaleFactor=1.1, minNeighbors=5, minSize=mn)
            t = frame_i / fps
            if len(faces):
                def score(f):
                    x, y, fw, fh = f
                    area = fw * fh
                    if prev is None:
                        return area
                    cx = (x + fw / 2) / sw
                    return area * (1.5 - min(1.0, abs(cx - prev)))   # preferir el rostro que ya seguíamos
                x, y, fw, fh = max(faces, key=score)
                cx, cy = (x + fw / 2) / sw, (y + fh / 2) / sh
                prev = cx
                raw.append((t, cx, cy))
            else:
                raw.append((t, None, None))
            if on_progress and duration:
                on_progress(min(0.999, t / duration))
        frame_i += 1
    cap.release()

    found = [r for r in raw if r[1] is not None]
    rate = len(found) / len(raw) if raw else 0.0
    if not found:
        return {"track": [], "detection_rate": 0.0, "samples": len(raw)}

    # Relleno de huecos (se mantiene la última posición conocida) + mediana de 5 muestras
    filled: list[tuple[float, float, float]] = []
    last = (found[0][1], found[0][2])
    for t, cx, cy in raw:
        if cx is not None:
            last = (cx, cy)
        filled.append((t, last[0], last[1]))
    med = []
    for i in range(len(filled)):
        win = filled[max(0, i - 2): i + 3]
        xs = sorted(p[1] for p in win)
        ys = sorted(p[2] for p in win)
        med.append((filled[i][0], xs[len(xs) // 2], ys[len(ys) // 2]))

    # Cámara virtual: se mueve solo si el sujeto sale de la zona muerta, con suavizado
    cam_x, cam_y = med[0][1], med[0][2]
    path_pts: list[list[float]] = []
    for t, x, y in med:
        if abs(x - cam_x) > deadzone:
            cam_x += (x - cam_x) * smoothing
        if abs(y - cam_y) > deadzone:
            cam_y += (y - cam_y) * smoothing
        path_pts.append([round(float(t), 3), round(float(cam_x), 4), round(float(cam_y), 4)])
    track = _rdp(path_pts, 0.01)
    return {"track": track, "detection_rate": round(rate, 3), "samples": len(raw)}
