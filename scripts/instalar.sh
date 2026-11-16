#!/usr/bin/env bash
# Instalador para macOS y Linux. Uso (desde la carpeta del proyecto):  bash scripts/instalar.sh
# Verifica Python 3.10+, Node 18+ y FFmpeg; instala lo que falte (Homebrew en macOS, apt en Linux),
# prepara el entorno de Python, compila la interfaz y crea el lanzador "iniciar".
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
say() { printf "\n\033[1;35m▸ %s\033[0m\n" "$1"; }
have() { command -v "$1" >/dev/null 2>&1; }

pkg_install() {
  if [[ "$(uname)" == "Darwin" ]]; then
    if ! have brew; then
      echo "Falta Homebrew. Instálalo desde https://brew.sh y vuelve a ejecutar este script."; exit 1
    fi
    brew install "$@"
  elif have apt-get; then
    sudo apt-get update -q && sudo apt-get install -y "$@"
  else
    echo "Instala manualmente: $*"; exit 1
  fi
}

py_ok() { have "$1" && "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; }

say "Revisando Python 3.10 o superior"
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do py_ok "$c" && { PY="$c"; break; }; done
if [[ -z "$PY" ]]; then
  if [[ "$(uname)" == "Darwin" ]]; then pkg_install python@3.12; else pkg_install python3 python3-venv; fi
  for c in python3.12 python3; do py_ok "$c" && { PY="$c"; break; }; done
fi
[[ -n "$PY" ]] || { echo "No se pudo instalar Python 3.10+"; exit 1; }
echo "OK: $($PY --version)"

say "Revisando Node.js 18 o superior"
if ! have node || [[ "$(node -p 'process.versions.node.split(".")[0]')" -lt 18 ]]; then
  if [[ "$(uname)" == "Darwin" ]]; then pkg_install node; else pkg_install nodejs npm; fi
fi
echo "OK: node $(node --version)"

say "Revisando FFmpeg"
have ffmpeg && have ffprobe || pkg_install ffmpeg
echo "OK: $(ffmpeg -hide_banner -version | head -1)"

say "Creando entorno de Python (backend/.venv)"
[[ -d backend/.venv ]] || "$PY" -m venv backend/.venv
backend/.venv/bin/python -m pip install -q --upgrade pip
backend/.venv/bin/python -m pip install -q -r backend/requirements.txt

say "Compilando la interfaz"
(cd frontend && npm ci --no-audit --no-fund --loglevel=error && npm run build --silent)

say "Creando el lanzador"
LAUNCH="$ROOT/iniciar.command"
cat > "$LAUNCH" <<LAUNCHER
#!/usr/bin/env bash
cd "$ROOT/backend" && exec ./.venv/bin/python -m app
LAUNCHER
chmod +x "$LAUNCH"
ln -sf "$LAUNCH" "$ROOT/iniciar"

say "Listo"
echo "Para abrir el editor: doble clic en iniciar.command (macOS) o ejecuta  $ROOT/iniciar"
echo "La primera transcripción descarga el modelo de Whisper (~145 MB)."
