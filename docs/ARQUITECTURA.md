# Smart Video Editor — Arquitectura

Documento de diseño. Cubre los puntos 1 a 5 de la metodología: análisis de la
arquitectura propuesta, estructura de carpetas, dependencias y riesgos, diseño
de componentes de interfaz y plan de implementación por etapas.

---

## 1. Análisis de la arquitectura propuesta

La pila propuesta (React + TypeScript / FastAPI / FFmpeg / Faster-Whisper /
PySceneDetect / OpenCV / SQLite) es correcta para un editor local. Mantengo
todas las piezas y agrego cuatro decisiones de diseño que cambian cómo se
conectan:

### 1.1 Edición no destructiva basada en una EDL (lista de decisiones)

El proyecto **nunca** guarda video procesado como fuente de verdad. Guarda un
documento JSON (versionado, dentro de SQLite) con:

| Campo | Contenido | Tiempo de referencia |
|---|---|---|
| `media` | ruta del original, duración, resolución, FPS, códecs | — |
| `cuts[]` | cortes `{start, end, kind, enabled}` | tiempo de la **fuente** |
| `captions[]` | frases con palabras y sus tiempos | tiempo de la **fuente** |
| `format` | relación de aspecto, modo de reencuadre, offset | — |
| `subtitle_style` | tipografía, colores, contorno, posición | — |

Consecuencias:

- **Recuperar un corte** = poner `enabled: false`. No se pierde nada.
- **Cambiar de 16:9 a 9:16** = cambiar un campo. No se reconstruye nada.
- **Sincronía garantizada**: subtítulos y cortes viven en el mismo eje de
  tiempo (la fuente). Al exportar, una sola función (`timeline.py` /
  `timemap.ts`) traduce tiempo-fuente → tiempo-salida para video, audio y
  subtítulos a la vez.
- El original se abre solo en lectura; todo lo generado va a la carpeta del
  proyecto.

### 1.2 Previsualización sin render

Renderizar cada cambio sería lento en videos largos. El monitor reproduce un
**proxy** (H.264 ≤720p, keyframe cada 1 s para saltos rápidos) y aplica la EDL
en vivo:

- Al entrar en un corte activo, el reproductor salta al final del corte.
- El formato se simula con CSS (`object-fit` + `object-position`, o fondo
  desenfocado).
- Los subtítulos se dibujan como overlay HTML con las mismas reglas que el
  archivo ASS que usa FFmpeg al exportar.

FFmpeg solo trabaja en: proxy, forma de onda, miniaturas, detección de
silencios y exportación.

### 1.3 Motor de trabajos en segundo plano

Toda operación pesada (proxy, transcripción, auto-edición, exportación) es un
**job** con estado persistido en SQLite: `queued → running → done | failed |
canceled`, progreso 0–1 y mensaje. El progreso de FFmpeg sale de
`-progress pipe:1`; el de Whisper, del avance de segmentos. Cancelar mata el
proceso FFmpeg o corta el bucle de Whisper. Si la app se cierra con jobs
corriendo, al reiniciar quedan marcados como `failed (interrumpido)`.

### 1.4 Desktop: app web local primero, contenedor nativo después

Etapa 1: el backend sirve el frontend compilado en `http://127.0.0.1:8765` y
abre el navegador. Ventajas: un solo proceso, cero dependencias extra, fácil
de depurar.
Etapa posterior: empaquetar con **Tauri** (más liviano que Electron, ~10 MB vs
~150 MB) lanzando el backend Python como *sidecar* compilado con PyInstaller.
Tauri además da diálogos nativos de archivos (rutas reales sin copiar videos
de varios GB).

### 1.5 Exportación exacta con `trim/atrim + concat`

Se evaluó `select/aselect` (más simple) y se descartó: el audio se corta por
bloques de ~21 ms y el desfase se **acumula** con cada corte (con 200 cortes
puede superar 1 s). `trim/atrim` es exacto a nivel de muestra. Además, cada
borde de segmento se ajusta a la grilla de frames del FPS de salida, para que
la duración de audio y video de cada segmento sea idéntica. El grafo se pasa
por archivo (`-filter_complex_script`) para soportar cientos de segmentos.

### 1.6 Transiciones sin alterar la duración (etapa 4)

Las transiciones viven en las **uniones**: el punto donde termina un segmento conservado y empieza
el siguiente. Una unión la crea un corte, o una **división** (corte de longitud cero que no quita
material: sirve para poner una transición en un cambio de escena).

- **Cruce con solapamiento** (`xfade`/`acrossfade`): cada lado se extiende hacia el interior del
  corte la mitad de la duración (“handles”) y se superponen. La duración total y la posición de cada
  unión no cambian, así que subtítulos y audio no se mueven. Sin material eliminado (divisiones) no
  hay solapamiento: disolución y deslizamiento se omiten y el render lo informa.
- **Efectos en el tiempo** sobre la salida ya reencuadrada, con filtros rápidos: `eq` para fundido
  a negro y flash (fórmula exacta hacia el negro 16 / blanco 235 de video), `scale+crop` con
  `eval=frame` para zoom, `gblur` controlado por `sendcmd` para desenfoque. La intensidad es real.
- Se descartaron las transiciones personalizadas píxel a píxel de `xfade`: medidas en 1080p tardan
  5–8 s cada una contra 0,6 s de las nativas.

### 1.7 Seguimiento de rostro como “cámara virtual” (etapa 3)

OpenCV (clasificador Haar incluido en `opencv-python-headless` 4.x; la versión 5 ya no lo trae)
muestrea el proxy 4 veces por segundo. La trayectoria se rellena, se filtra con mediana, pasa por una
cámara con zona muerta (2 % del ancho) y suavizado, y se simplifica con Ramer–Douglas–Peucker
(típicamente 4–20 puntos). En el render, la `x` del `crop` es una expresión lineal por tramos en el
tiempo de salida, con saltos exactos en las uniones.

### 1.8 Audio (etapa 5)

Paso alto → reducción de ruido (`afftdn` con el piso de ruido **medido** en la pausa más larga: el
modo de seguimiento automático casi no actúa, se midió 1,4 dB vs 30 dB) → cortes con micro-fundidos
anti-clic de 6 ms → cruces → ganancia de voz → música (envolvente de volumen y fundidos evaluados
por cuadro, ducking con `sidechaincompress` escuchando la voz) → normalización → fundidos globales →
marcas de tiempo continuas y duración exacta del video.

---

## 2. Estructura de carpetas

```
smart-video-editor/
├── README.md                  Cómo instalar, ejecutar y estado de cada función
├── docs/ARQUITECTURA.md       Este documento
├── scripts/
│   ├── dev.sh                 Backend + frontend en modo desarrollo
│   └── make_test_video.sh     Genera un video de prueba con voz y silencios
├── backend/
│   ├── requirements.txt
│   ├── app/
│   │   ├── __main__.py        `python -m app` → servidor + abre navegador
│   │   ├── main.py            FastAPI, rutas, archivos estáticos
│   │   ├── config.py          Rutas de trabajo, puertos, perfiles
│   │   ├── db.py              SQLite (proyectos, jobs)
│   │   ├── schemas.py         Modelo del documento de proyecto (Pydantic)
│   │   ├── jobs.py            Cola de jobs, progreso, cancelación
│   │   ├── api/               Endpoints REST (projects, media, jobs, system)
│   │   └── engine/            Motor audiovisual, sin dependencias de FastAPI
│   │       ├── ffmpeg.py      Ejecutar FFmpeg con progreso y cancelación
│   │       ├── media.py       ffprobe, proxy, forma de onda, miniaturas
│   │       ├── silence.py     silencedetect
│   │       ├── autoedit.py    Reglas de corte inteligente
│   │       ├── transcribe.py  Faster-Whisper con timestamps por palabra
│   │       ├── timeline.py    Segmentos conservados y mapeo de tiempos
│   │       ├── subtitles.py   Agrupación en frases, SRT, ASS
│   │       ├── reframe.py     Filtros de formato 9:16 / 16:9 / 1:1
│   │       ├── scenes.py      Cambios de escena (PySceneDetect)
│   │       ├── facetrack.py   Seguimiento de rostro (OpenCV)
│   │       ├── audio.py       Piso de ruido para la reducción de ruido
│   │       └── render.py      Exportación final y render parcial (previsualización exacta)
│   └── packaging/launcher.py  Punto de entrada del ejecutable (PyInstaller)
│   └── tests/                 pytest por módulo + prueba de API completa
└── frontend/
    ├── package.json, vite.config.ts, tsconfig.json
    └── src/
        ├── api/               Cliente HTTP tipado
        ├── lib/               timemap.ts, formato de tiempo, estilos
        ├── state/             Store del proyecto + autoguardado
        └── components/        Paneles (ver sección 4)
```

---

## 3. Dependencias y riesgos

### 3.1 Dependencias

| Dependencia | Uso | Licencia | Nota |
|---|---|---|---|
| FFmpeg ≥ 6 (con libx264, libass) | Todo el procesamiento | GPL (por x264) | Externo; la app lo detecta y avisa si falta |
| faster-whisper 1.2 (CTranslate2) | Transcripción | MIT | Modelos de 75 MB (tiny) a 3 GB (large-v3) desde HuggingFace |
| FastAPI + Uvicorn | API local | MIT/BSD | |
| SQLite (stdlib) | Persistencia | Dominio público | |
| React 18 + Vite + TypeScript | Interfaz | MIT | Sin librería de UI, CSS propio |
| PySceneDetect, OpenCV | Escenas, reencuadre por rostro | BSD/Apache | **Etapa 3**, no se instalan en el MVP |

### 3.2 Riesgos y mitigación

| # | Riesgo | Impacto | Mitigación |
|---|---|---|---|
| R1 | Desincronía audio/video/subtítulos tras muchos cortes | Alto | Un solo mapeo de tiempo; bordes ajustados a grilla de frames; `trim/atrim`; test automático que mide la duración de audio y video de la exportación |
| R2 | Videos con FPS variable (celulares) | Alto | Filtro `fps=` antes del corte en exportación; el proxy se genera a FPS constante |
| R3 | Whisper lento en CPU con videos largos | Medio | Modelo seleccionable (tiny/base/small/medium); VAD integrado; job cancelable con progreso; GPU automática si hay CUDA |
| R4 | Timestamps de palabras de Whisper imprecisos (±100 ms) | Medio | Los cortes se basan en `silencedetect` (señal real) y las palabras solo actúan como protección; margen configurable |
| R5 | El navegador no reproduce MKV/HEVC/ProRes | Medio | Proxy H.264 obligatorio para la previsualización |
| R6 | Formatos/códecs raros o archivos corruptos | Medio | ffprobe valida antes de importar; error claro al usuario |
| R7 | Grafos de FFmpeg enormes (cientos de cortes) | Medio | `-filter_complex_script`; probado con decenas de segmentos |
| R8 | Fuentes de subtítulos distintas entre preview y export | Bajo | Se listan solo fuentes instaladas (`fc-list`), que usan tanto el navegador local como libass |
| R9 | Autoguardado pisando resultados de un job | Medio | Revisión (`rev`) por proyecto: el servidor rechaza escrituras con revisión vieja (409) y el cliente recarga |
| R10 | Disco lleno por proxies y exportaciones | Bajo | Todo en la carpeta del proyecto; borrar proyecto borra sus archivos (nunca el original) |
| R11 | Licencia GPL de FFmpeg con x264 al distribuir | Legal | Distribuir FFmpeg como binario separado, no enlazado |

---

## 4. Componentes de la interfaz

Diseño oscuro de 3 zonas + timeline inferior:

```
┌───────────────────────────────────────────────────────────────────────────┐
│ TopBar: [☰ Proyectos] Nombre del proyecto · guardado ✓   [✨ Auto-editar] [⇩ Exportar] │
├────────────┬──────────────────────────────────────┬───────────────────────┤
│ Projects   │            Monitor                    │ Inspector (pestañas)  │
│ Panel      │   ┌──────────┐                        │ ▸ Auto-edición        │
│ (lista,    │   │  9:16    │  overlay subtítulos    │ ▸ Subtítulos          │
│  nuevo,    │   │ preview  │                        │ ▸ Estilo              │
│  borrar)   │   └──────────┘                        │ ▸ Formato             │
│            │ Transport: ⏮ ▶ ⏭  00:12.4 / 01:30  ☑ aplicar cortes │ ▸ Exportar │
├────────────┴──────────────────────────────────────┴───────────────────────┤
│ Timeline: regla de tiempo · zoom                                          │
│  V1  ▕▓▓▓▓▓░░░▓▓▓▓▓▓▓░░▓▓▓▓▓▕   miniaturas + cortes (gris = eliminado)     │
│  A1  ▕∿∿∿∿∿___∿∿∿∿∿∿∿__∿∿∿∿∿▕   forma de onda                              │
│  S1  ▕[Hola a ][todos]  [hoy ]▕  bloques de subtítulos                      │
├───────────────────────────────────────────────────────────────────────────┤
│ JobBar: Transcribiendo… 43% [Cancelar]                                     │
└───────────────────────────────────────────────────────────────────────────┘
```

| Componente | Responsabilidad |
|---|---|
| `ProjectsPanel` | Listar, crear, abrir, borrar proyectos |
| `ImportDropzone` | Arrastrar/soltar o elegir MP4/MOV/MKV; validación de extensión |
| `Monitor` | Video proxy, simulación de formato, overlay de subtítulos, salto de cortes |
| `Transport` | Play/pausa, ±1 s, ±1 frame, tiempo fuente/salida, interruptor de cortes |
| `Timeline` | Regla, zoom, pistas V/A/S, cabezal; clic en corte = activar/recuperar; arrastrar bordes |
| `AutoEditPanel` | Parámetros de silencio y botón de auto-edición; lista de cortes |
| `SubtitlesPanel` | Transcribir (modelo, idioma), lista editable de frases, exportar SRT |
| `StylePanel` | Fuente, tamaño, colores, contorno, sombra, posición, preajustes, resaltado de palabra |
| `FormatPanel` | 9:16 / 16:9 / 1:1, reencuadre (recorte o fondo desenfocado), posición horizontal |
| `ExportPanel` | Perfil de plataforma, resolución, FPS, subtítulos incrustados/SRT, normalizar audio |
| `JobBar` | Jobs activos con progreso y botón cancelar; errores |

---

## 5. Plan por etapas

| Etapa | Contenido | Criterio de salida |
|---|---|---|
Estado al 16/11/2026: etapas 0 a 5 implementadas y probadas; etapa 6 parcial (ejecutable
PyInstaller probado en Linux; envoltorio Tauri e instaladores pendientes).

| **0. Base** | Estructura, SQLite, jobs con progreso/cancelación, ffprobe | Tests de jobs y probe pasan |
| **1. MVP** | Importación, proxy, forma de onda, miniaturas, transcripción, auto-edición por silencios, cortes recuperables, subtítulos editables con estilo, 9:16 / 16:9 / 1:1, exportación MP4 + SRT, autoguardado | Exportación real verificada: duración = suma de segmentos, audio y video alineados, subtítulos en tiempo de salida |
| **2. Edición avanzada** ✅ | Deshacer/rehacer, divisiones, imán, animaciones de subtítulos (pop, fundido, subir, palabra a palabra), 8 preajustes, importar proyecto y reconectar video | Tests de ASS, API de importación/reconexión, E2E de deshacer |
| **3. Análisis visual** ✅ | PySceneDetect, seguimiento de rostro con cámara virtual, zoom alternado | Escenas ±80 ms; rostro con 100 % de detección y error < 0,02 |
| **4. Transiciones** ✅ | Las 6 transiciones, por defecto o individuales, duración, intensidad, dirección; previsualización exacta por render parcial | Duración y sincronía preservadas; luminancia medida en la unión |
| **5. Audio** ✅ | Reducción de ruido, paso alto, música, envolvente, ducking, fundidos | Piso de ruido −30 dB; ducking ≥ 6 dB en banda medida |
| 6. Empaquetado (parcial) | Ejecutable PyInstaller con FFmpeg incluido ✅ · Tauri, firma e instaladores Windows/macOS ⏳ | Ejecutable probado en Linux sin FFmpeg en el sistema |
