#!/usr/bin/env bash
# Genera un video de prueba 1280x720 30fps con voz en español y pausas conocidas.
# Uso: scripts/make_test_video.sh salida.mp4
# Requiere: ffmpeg, espeak-ng
set -euo pipefail
OUT="${1:-test_video.mp4}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

say() { espeak-ng -v es-419 -s 150 -w "$TMP/$1.wav" "$2"; }
say p1 "Hola a todos, bienvenidos al canal."
say p2 "Hoy vamos a probar el editor automático."
say p3 "Esta frase tiene una pausa corta"
say p4 "en el medio."
say p5 "Y aquí termina la prueba. Gracias por ver."

sil() { ffmpeg -v error -f lavfi -i "anullsrc=r=22050:cl=mono" -t "$2" -c:a pcm_s16le "$TMP/$1.wav"; }
sil s0 1.0   # silencio inicial
sil s1 1.8   # pausa larga  -> debe cortarse
sil s2 2.2   # pausa larga  -> debe cortarse
sil s3 0.35  # pausa corta  -> NO debe cortarse
sil s4 1.5   # pausa larga  -> debe cortarse
sil s5 1.2   # silencio final

printf "file '%s'\n" s0.wav p1.wav s1.wav p2.wav s2.wav p3.wav s3.wav p4.wav s4.wav p5.wav s5.wav > "$TMP/list.txt"
ffmpeg -v error -f concat -safe 0 -i "$TMP/list.txt" -ar 48000 -ac 2 "$TMP/audio.wav"
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$TMP/audio.wav")
ffmpeg -v error -y -f lavfi -i "testsrc2=size=1280x720:rate=30" -i "$TMP/audio.wav" -t "$DUR" \
  -c:v libx264 -preset veryfast -pix_fmt yuv420p -c:a aac -b:a 128k -shortest "$OUT"
echo "$OUT ($DUR s)"
