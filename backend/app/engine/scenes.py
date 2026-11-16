"""Detección de cambios de escena con PySceneDetect (ContentDetector)."""
from __future__ import annotations

from typing import Callable, Optional


def detect_scenes(path: str, duration: float, threshold: float = 27.0, min_scene_len: float = 0.6, *,
                  on_progress: Optional[Callable[[float], None]] = None, cancel_event=None) -> list[float]:
    """Devuelve los instantes (s) donde empieza una escena nueva, sin incluir el 0."""
    from scenedetect import ContentDetector, SceneManager, open_video

    from .ffmpeg import OperationCanceled

    video = open_video(path)
    fps = float(video.frame_rate) or 30.0
    sm = SceneManager()
    sm.auto_downscale = True
    sm.add_detector(ContentDetector(threshold=threshold, min_scene_len=max(1, round(min_scene_len * fps))))
    chunk = max(1, round(fps * 20))
    while True:
        if cancel_event is not None and cancel_event.is_set():
            raise OperationCanceled()
        processed = sm.detect_scenes(video=video, duration=chunk)
        if on_progress and duration:
            on_progress(min(0.999, video.position.seconds / duration))
        if processed == 0 or video.position.seconds >= duration - 1 / fps:
            break
    scenes = sm.get_scene_list(start_in_scene=True)
    return [round(s.seconds, 3) for s, _ in scenes[1:]]
