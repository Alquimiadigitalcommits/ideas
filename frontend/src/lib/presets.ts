import type { SubtitleStyle } from "../api/types";

type Preset = Partial<SubtitleStyle> & { label: string };

export const SUBTITLE_PRESETS: Record<string, Preset> = {
  clasico: { label: "Clásico", font_family: "Inter", font_size: 64, bold: true, uppercase: false,
    primary_color: "#FFFFFF", highlight_color: "#FFD400", highlight_words: true, outline_color: "#000000",
    outline_width: 4, shadow: 2, position_y: 0.78 },
  impacto: { label: "Impacto (MAYÚSCULAS)", font_family: "Inter", font_size: 80, bold: true, uppercase: true,
    primary_color: "#FFFFFF", highlight_color: "#22E06B", highlight_words: true, outline_color: "#000000",
    outline_width: 7, shadow: 0, position_y: 0.62 },
  minimal: { label: "Minimal", font_family: "Inter", font_size: 52, bold: false, uppercase: false,
    primary_color: "#FFFFFF", highlight_color: "#FFFFFF", highlight_words: false, outline_color: "#000000",
    outline_width: 2, shadow: 3, position_y: 0.86 },
  gamer: { label: "Gamer", font_family: "JetBrains Mono", font_size: 64, bold: true, uppercase: true,
    primary_color: "#E8F7FF", highlight_color: "#53FC18", highlight_words: true, outline_color: "#120024",
    outline_width: 6, shadow: 4, position_y: 0.74 },
  karaoke: { label: "Karaoke rosa", font_family: "Inter", font_size: 70, bold: true, uppercase: false,
    primary_color: "#FFFFFF", highlight_color: "#FF4FB4", highlight_words: true, outline_color: "#2A0019",
    outline_width: 5, shadow: 2, position_y: 0.7 },
};
