# Smart Video Editor

Editor de video local que importa un video, lo transcribe, propone cortes de silencios,
genera subtítulos editables con estilo y exporta para TikTok, Reels, Shorts y YouTube con FFmpeg.

Estado: **MVP (etapa 1)**. Diseño completo, riesgos y plan de etapas en [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md).

![Editor](docs/captura-editor.png)

## Requisitos

| Herramienta | Versión probada | Para qué |
|---|---|---|
| Python | 3.13 (≥ 3.10) | Motor y API |
| Node.js | 22 (≥ 18) | Compilar la interfaz |
| FFmpeg + FFprobe | 6.1, con `libx264` y `libass` | Todo el procesamiento |
| Conexión a internet | solo la primera vez por modelo | Descarga del modelo Whisper desde HuggingFace (tiny 75 MB · base 145 MB · small 480 MB) |

FFmpeg: en Windows `winget install Gyan.FFmpeg`; en macOS `brew install ffmpeg`; en Linux `apt install ffmpeg`.

## Instalación

```bash
cd backend
```

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

```bash
pip install -r requirements.txt
```

```bash
cd ../frontend && npm install && npm run build
```

## Uso

```bash
cd backend && python -m app
```

Abre `http://127.0.0.1:8765` en el navegador. Los proyectos, proxies y exportaciones se guardan
en `~/SmartVideoEditor` (cambiable con la variable `SVE_WORKSPACE`). Los videos originales
nunca se modifican.

Flujo típico:

1. **+ Nuevo** proyecto → arrastra un MP4/MOV/MKV (o usa la ruta local para archivos grandes, sin copiarlos).
2. **Subtítulos → Transcribir** (modelo `base` por defecto, español).
3. **✨ Auto-editar**: detecta pausas y las marca como cortes (rayado rojo en la línea de tiempo).
4. Revisa: doble clic en un corte para recuperarlo, arrastra sus bordes, o marca un rango con **I** / **O** y pulsa **X** para cortar a mano.
5. **Formato** 9:16 / 16:9 / 1:1 y **Estilo** de subtítulos. La vista previa refleja ambos en vivo.
6. **Exportar**: elige perfil de plataforma → MP4 (+ SRT opcional).

### Atajos de teclado

| Tecla | Acción |
|---|---|
| Espacio | Reproducir / pausa |
| ← / → (Shift: ×5) | −1 s / +1 s |
| , / . | −1 / +1 frame |
| I / O / X | Marcar entrada / salida / eliminar el rango marcado |
| Supr | Recuperar o volver a cortar el corte seleccionado |
| Esc | Quitar selección y marcas |

### Desarrollo

```bash
scripts/dev.sh
```

Interfaz con recarga en caliente en `http://localhost:5173`.

## Pruebas

```bash
cd backend && python -m pytest -q
```

```bash
cd frontend && npm test && npm run typecheck
```

```bash
node e2e/smoke.cjs ruta/al/video.mp4 carpeta_capturas
```

El último requiere la app corriendo y Playwright instalado. Los tests de backend generan sus
propios videos de prueba con FFmpeg; los de voz usan `espeak-ng` (`scripts/make_test_video.sh`) y se
omiten si no está instalado.

Resultado al cierre de esta etapa: 43 tests de backend, 5 de frontend y la prueba E2E en navegador, todos pasando.

## Qué funciona (verificado con tests)

| Función | Estado | Cómo se verificó |
|---|---|---|
| Importar MP4 / MOV / MKV (subida o ruta local sin copiar) | ✅ | API + E2E; rechaza extensiones no soportadas y archivos corruptos |
| Análisis: duración, resolución, FPS, códecs, rotación | ✅ | `test_media.py` |
| Proxy H.264 ≤720p, miniaturas, forma de onda (job en segundo plano) | ✅ | `test_media.py` |
| Transcripción Faster-Whisper con tiempos por palabra, modelo e idioma elegibles | ✅ | `test_transcribe.py` (modelo tiny) |
| Detección de silencios (FFmpeg `silencedetect`) | ✅ | Posición de silencios con error ≤ 50 ms |
| Cortes inteligentes: aire configurable, más aire a mitad de frase, protección de palabras, fusión de sonidos sueltos | ✅ | `test_autoedit.py` |
| Revisar, recuperar, ajustar, borrar y crear cortes manuales | ✅ | E2E |
| Previsualización con salto de cortes en vivo (sin render) | ✅ | E2E |
| Subtítulos: edición de texto con retiming automático, borrar, reagrupar por palabras/caracteres | ✅ | `test_subtitles.py`, `timemap.test.ts` |
| Estilo: fuente instalada, tamaño, negrita, mayúsculas, colores, contorno, sombra, posición, 5 preajustes | ✅ | Comparación vista previa vs fotograma exportado |
| Resaltado de la palabra que se dice (karaoke) | ✅ | ASS con un evento por palabra |
| Exportar SRT ajustado a los cortes | ✅ | `test_render.py`, `test_api.py` |
| Formatos 9:16, 16:9, 1:1 con recorte (posición X/Y + zoom), fondo desenfocado o barras | ✅ | Dimensiones de salida verificadas |
| Exportación MP4 H.264/AAC con perfiles TikTok, Reels, Shorts, YouTube, Instagram cuadrado; resolución y FPS configurables | ✅ | `test_render.py` |
| Normalización de volumen a −14 LUFS | ✅ | Medido: −14,9 LUFS |
| Sincronía audio/video tras cortes | ✅ | Diferencia < 10 ms con cortes reales; < 70 ms con 41 segmentos; sin saltos en el audio |
| Jobs con progreso, cancelación y limpieza de archivos parciales | ✅ | `test_api.py::test_upload_and_cancel_export` |
| Autoguardado con control de versiones (evita pisar resultados de un proceso) | ✅ | Conflicto 409 probado |
| Persistencia de proyectos (SQLite) y copia `.json` descargable | ✅ | E2E: recarga de página |

## Pendiente (no implementado)

| Función | Etapa |
|---|---|
| Deshacer / rehacer | 2 |
| Animaciones de subtítulos (pop, bounce, máquina de escribir) | 2 |
| Importar un proyecto `.json` | 2 |
| Detección de escenas (PySceneDetect) | 3 |
| Reencuadre automático siguiendo rostros (OpenCV) | 3 |
| Transiciones: fundido, disolución, zoom, desenfoque, deslizamiento, flash | 4 |
| Reducción de ruido, música de fondo, mezcla, ducking, fundidos de audio | 5 |
| Aplicación de escritorio empaquetada (Tauri) con FFmpeg incluido | 6 |

## Limitaciones conocidas

- **Videos largos**: la arquitectura está pensada para ellos (proxy, grafos por archivo, waveform por tramos), pero en esta etapa solo se probó con videos de 8 a 22 s. Whisper `base` procesó 21,7 s de audio en 2,1 s en una CPU de 4 núcleos; extrapolado, 1 h de audio tomaría unos 6 min (estimación, audio limpio).
- **Subir un archivo lo copia** a la carpeta del proyecto (el navegador no entrega la ruta real). Para archivos de varios GB usa "usar desde su ubicación".
- **Volver a auto-editar** reemplaza los cortes de silencio (los manuales se conservan), así que se pierden los silencios que habías recuperado. **Volver a transcribir** reemplaza los subtítulos (pide confirmación si hay ediciones).
- La vista previa de subtítulos es HTML/CSS calibrado contra libass (factor 0,82). En Inter coincide en ±1 % de ancho; otras fuentes pueden variar unos píxeles.
- Se usa solo la primera pista de audio del archivo.
- Videos de FPS variable (celulares): la exportación fuerza FPS constante; no se ha probado aún con grabaciones reales de teléfono.
- Probado en Linux. Windows y macOS no se han probado todavía.
