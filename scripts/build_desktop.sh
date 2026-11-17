#!/usr/bin/env bash
# Construye el ejecutable autónomo (carpeta dist/SmartVideoEditor) con PyInstaller.
# Uso: scripts/build_desktop.sh [ruta_a_carpeta_con_ffmpeg_y_ffprobe]
# Si se indica una carpeta con ffmpeg/ffprobe, se copian dentro del paquete (dist/SmartVideoEditor/ffmpeg/).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SEP=":"; [[ "${OS:-}" == "Windows_NT" ]] && SEP=";"

(cd "$ROOT/frontend" && npm run build)
cd "$ROOT/backend"
python -m PyInstaller --noconfirm --clean --onedir --name SmartVideoEditor \
  --distpath "$ROOT/dist" --workpath "$ROOT/build/pyinstaller" --specpath "$ROOT/build" \
  --paths "$ROOT/backend" \
  --add-data "$ROOT/frontend/dist${SEP}frontend_dist" \
  --add-data "$ROOT/backend/app/assets/fonts${SEP}app/assets/fonts" \
  --collect-data fontTools --hidden-import app.selfcheck --hidden-import app.api.auto \
  --collect-data faster_whisper --collect-binaries ctranslate2 \
  --collect-submodules uvicorn --collect-data cv2 --collect-submodules scenedetect \
  --hidden-import app.main \
  "$ROOT/backend/packaging/launcher.py"

if [[ -n "${1:-}" ]]; then
  mkdir -p "$ROOT/dist/SmartVideoEditor/ffmpeg"
  cp "$1"/ffmpeg* "$1"/ffprobe* "$ROOT/dist/SmartVideoEditor/ffmpeg/"
fi
echo "Listo: $ROOT/dist/SmartVideoEditor/"
