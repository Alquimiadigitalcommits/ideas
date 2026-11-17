// Espejo de backend/app/schemas.py. Todos los tiempos en segundos de la FUENTE.
export interface MediaInfo {
  source_path: string;
  file_name: string;
  duration: number;
  width: number;
  height: number;
  fps: number;
  video_codec?: string | null;
  audio_codec?: string | null;
  has_audio: boolean;
  size_bytes: number;
  rotation: number;
}

export type TransitionType = "none" | "fade" | "dissolve" | "zoom" | "blur" | "slide" | "flash";

export interface Transition {
  type: TransitionType;
  duration: number;
  intensity: number;
  direction: "left" | "right" | "up" | "down";
}

export interface Cut {
  id: string;
  start: number;
  end: number;
  kind: "silence" | "manual" | "split";
  enabled: boolean;
  reason: string;
  transition?: Transition | null;
}

export interface Word {
  start: number;
  end: number;
  text: string;
  prob?: number;
}

export interface Caption {
  id: string;
  start: number;
  end: number;
  text: string;
  words: Word[];
  edited: boolean;
}

export interface SubtitleStyle {
  preset: string;
  font_family: string;
  font_size: number;
  bold: boolean;
  uppercase: boolean;
  primary_color: string;
  highlight_color: string;
  highlight_words: boolean;
  outline_color: string;
  outline_width: number;
  shadow: number;
  shadow_color: string;
  position_y: number;
  animation: "none" | "pop" | "fade" | "slide" | "typewriter";
  max_words: number;
  max_chars: number;
}

export type Aspect = "9:16" | "16:9" | "1:1";

export interface FormatSettings {
  aspect: Aspect;
  mode: "crop" | "blur" | "fit";
  offset_x: number;
  offset_y: number;
  zoom: number;
  track_enabled: boolean;
  track: [number, number, number][];
  jump_zoom: number;
}

export interface MusicTrack {
  path: string;
  file_name: string;
  duration: number;
  volume_db: number;
  start_offset: number;
  loop: boolean;
  fade_in: number;
  fade_out: number;
  ducking: boolean;
  ducking_amount: number;
}

export interface AudioSettings {
  voice_gain_db: number;
  denoise: boolean;
  denoise_strength: number;
  highpass: boolean;
  fade_in: number;
  fade_out: number;
  music: MusicTrack | null;
}

export interface AutoEditSettings {
  noise_db: number;
  min_silence: number;
  padding: number;
  mid_sentence_padding: number;
  min_keep: number;
  protect_words: boolean;
}

export interface ProjectDoc {
  schema_version: number;
  media: MediaInfo | null;
  proxy_ready: boolean;
  language: string | null;
  cuts: Cut[];
  captions: Caption[];
  subtitle_style: SubtitleStyle;
  format: FormatSettings;
  autoedit: AutoEditSettings;
  transition_default: Transition;
  scenes: number[];
  audio: AudioSettings;
}

export interface Project {
  id: string;
  name: string;
  created_at: number;
  updated_at: number;
  rev: number;
  doc: ProjectDoc;
  media_available?: boolean | null;
}

export type JobStatus = "queued" | "running" | "done" | "failed" | "canceled";

export interface Job {
  id: string;
  project_id: string | null;
  kind: "prepare" | "transcribe" | "autoedit" | "export" | string;
  status: JobStatus;
  progress: number;
  message: string;
  error?: string | null;
  result?: Record<string, any> | null;
  created_at: number;
  updated_at: number;
}

export interface ExportProfile {
  label: string;
  aspect: Aspect;
  short: number;
  fps: number;
  audio_kbps: number;
}

export interface HardwareProfile {
  threads: number;
  ram_gb: number;
  avx2: boolean;
  tier: "modesto" | "normal";
  whisper_model: string;
  export_preset: string;
}

export interface BundledFont {
  family: string;
  weight: number;
  file: string;
  css_scale: number;
}

export interface AutoRequest {
  platform: string;
  remove_silences: boolean;
  pace: "natural" | "dinamico";
  subtitles: boolean;
  burn_subtitles: boolean;
  subtitle_style: SubtitleStyle | null;
  face_track: boolean;
  enhance_audio: boolean;
  language: string | null;
}

export interface SystemInfo {
  ffmpeg: { ok: boolean; version: string | null };
  whisper: boolean;
  whisper_error: string | null;
  hardware: HardwareProfile;
  whisper_models: string[];
  default_whisper_model: string;
  profiles: Record<string, ExportProfile>;
  workspace: string;
}

export interface ExportRequest {
  profile: string;
  width?: number | null;
  height?: number | null;
  fps?: number | null;
  burn_subtitles: boolean;
  write_srt: boolean;
  normalize_audio: boolean;
  crf: number;
  preset: string;
  file_name?: string | null;
}

export interface ExportFile {
  name: string;
  size: number;
  mtime: number;
  path: string;
}
