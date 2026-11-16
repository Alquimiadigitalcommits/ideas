"""Documento de proyecto (EDL). Todos los tiempos están en segundos del archivo FUENTE."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1


class MediaInfo(BaseModel):
    source_path: str
    file_name: str
    duration: float
    width: int
    height: int
    fps: float
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    has_audio: bool = True
    size_bytes: int = 0
    rotation: int = 0


class Cut(BaseModel):
    id: str
    start: float
    end: float
    kind: Literal["silence", "manual"] = "silence"
    enabled: bool = True
    reason: str = ""


class Word(BaseModel):
    start: float
    end: float
    text: str
    prob: float = 1.0


class Caption(BaseModel):
    id: str
    start: float
    end: float
    text: str
    words: list[Word] = Field(default_factory=list)
    edited: bool = False


class SubtitleStyle(BaseModel):
    preset: str = "clasico"
    font_family: str = "Inter"
    font_size: int = 64          # px relativos a una salida de 1920 px de alto
    bold: bool = True
    uppercase: bool = False
    primary_color: str = "#FFFFFF"
    highlight_color: str = "#FFD400"
    highlight_words: bool = True
    outline_color: str = "#000000"
    outline_width: float = 4.0
    shadow: float = 2.0
    shadow_color: str = "#000000"
    position_y: float = 0.78     # 0 = arriba, 1 = abajo (centro de la línea)
    max_words: int = 4           # palabras por bloque al agrupar
    max_chars: int = 28


class FormatSettings(BaseModel):
    aspect: Literal["9:16", "16:9", "1:1"] = "9:16"
    mode: Literal["crop", "blur", "fit"] = "crop"
    offset_x: float = 0.5        # 0 = izquierda, 1 = derecha (solo en crop)
    offset_y: float = 0.5
    zoom: float = 1.0


class AutoEditSettings(BaseModel):
    noise_db: float = -35.0       # umbral de silencio
    min_silence: float = 0.6      # s mínimos para considerar silencio
    padding: float = 0.15         # s de aire que se conservan a cada lado
    mid_sentence_padding: float = 0.25  # más aire si la frase continúa
    min_keep: float = 0.25        # segmentos conservados más cortos se fusionan
    protect_words: bool = True    # nunca cortar encima de una palabra transcrita


class ProjectDoc(BaseModel):
    schema_version: int = SCHEMA_VERSION
    media: Optional[MediaInfo] = None
    proxy_ready: bool = False
    language: Optional[str] = None
    cuts: list[Cut] = Field(default_factory=list)
    captions: list[Caption] = Field(default_factory=list)
    subtitle_style: SubtitleStyle = Field(default_factory=SubtitleStyle)
    format: FormatSettings = Field(default_factory=FormatSettings)
    autoedit: AutoEditSettings = Field(default_factory=AutoEditSettings)


class Project(BaseModel):
    id: str
    name: str
    created_at: float
    updated_at: float
    rev: int
    doc: ProjectDoc


class ExportRequest(BaseModel):
    profile: str = "tiktok"
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    burn_subtitles: bool = True
    write_srt: bool = True
    normalize_audio: bool = False
    crf: int = 20
    preset: str = "medium"
    file_name: Optional[str] = None


class TranscribeRequest(BaseModel):
    model: str = "base"
    language: Optional[str] = "es"   # None = autodetectar


class Job(BaseModel):
    id: str
    project_id: Optional[str]
    kind: str
    status: Literal["queued", "running", "done", "failed", "canceled"]
    progress: float
    message: str
    error: Optional[str] = None
    result: Optional[dict] = None
    created_at: float
    updated_at: float
