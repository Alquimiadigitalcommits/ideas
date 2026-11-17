# Instalador de Smart Video Editor para Windows 10/11.
# Lo mas facil: doble clic en INSTALAR.bat (en la carpeta principal del proyecto).
# Instala lo que falte (Python 3.12, FFmpeg, Microsoft Visual C++ Redistributable), prepara el editor,
# descarga el modelo de transcripcion, ejecuta una verificacion y crea el acceso directo en el escritorio.
# Funciona con o sin winget. Este archivo es solo ASCII a proposito (Windows PowerShell 5.1).

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"   # la barra de progreso hace muy lentas las descargas en PS 5.1
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Tmp = Join-Path $env:TEMP "sve-instalador"
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null

function Say($m) { Write-Host ""; Write-Host "==> $m" -ForegroundColor Cyan }
function Ok($m) { Write-Host "    OK: $m" -ForegroundColor Green }
function Fail($m) {
  Write-Host ""; Write-Host "ERROR: $m" -ForegroundColor Red
  Write-Host "Copia este mensaje y enviaselo a quien te ayuda con la instalacion."
  Read-Host "Presiona Enter para cerrar"; exit 1
}
function Have($c) { [bool](Get-Command $c -ErrorAction SilentlyContinue) }
function Refresh-Path {
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}
function Download($url, $dest) {
  Write-Host "    Descargando $url"
  try { Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing } catch { Fail "No se pudo descargar $url. Revisa tu conexion a internet. $_" }
}
$HasWinget = Have winget
function Winget($id) {
  winget install --id $id -e --accept-source-agreements --accept-package-agreements --silent
  Refresh-Path
}

# ---------------------------------------------------------------- Python 3.10 - 3.13
Say "Python"
function Find-Python {
  foreach ($v in @("3.12", "3.11", "3.13", "3.10")) {
    if (Have py) {
      & py "-$v" -c "import sys" 2>$null
      if ($LASTEXITCODE -eq 0) { return @("py", "-$v") }
    }
  }
  if (Have python) {
    & python -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) { return @("python") }
  }
  return $null
}
$Py = Find-Python
if (-not $Py) {
  Write-Host "    Instalando Python 3.12..."
  if ($HasWinget) { Winget "Python.Python.3.12" }
  $Py = Find-Python
  if (-not $Py) {
    $exe = Join-Path $Tmp "python-3.12.10-amd64.exe"
    Download "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe" $exe
    Start-Process -Wait -FilePath $exe -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_launcher=1", "Include_test=0"
    Refresh-Path
    $Py = Find-Python
  }
  if (-not $Py) { Fail "No se pudo instalar Python 3.12. Instalalo desde https://www.python.org/downloads/ marcando 'Add python.exe to PATH' y vuelve a ejecutar INSTALAR.bat." }
}
$PyExe = $Py[0]; $PyArgs = @(); if ($Py.Count -gt 1) { $PyArgs = $Py[1..($Py.Count - 1)] }
Ok (& $PyExe @PyArgs --version)

# ---------------------------------------------------------------- Visual C++ Redistributable
# La transcripcion (ctranslate2, onnxruntime) necesita msvcp140.dll y msvcp140_1.dll, que Python no trae.
Say "Componentes de Windows para la transcripcion (Visual C++ Redistributable)"
Write-Host "    Si Windows pide permiso de administrador, acepta."
$vcOk = $false
if ($HasWinget) {
  Winget "Microsoft.VCRedist.2015+.x64"
  if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq -1978335189) { $vcOk = $true }   # instalado o ya presente
}
if (-not $vcOk) {
  $vc = Join-Path $Tmp "vc_redist.x64.exe"
  Download "https://aka.ms/vs/17/release/vc_redist.x64.exe" $vc
  $p = Start-Process -Wait -PassThru -FilePath $vc -ArgumentList "/install", "/quiet", "/norestart"
  if (@(0, 1638, 3010) -notcontains $p.ExitCode) { Fail "No se pudo instalar Visual C++ Redistributable (codigo $($p.ExitCode))." }
}
if (-not (Test-Path "$env:WINDIR\System32\msvcp140_1.dll")) { Fail "Visual C++ Redistributable no quedo instalado (falta msvcp140_1.dll)." }
Ok "Visual C++ Redistributable"

# ---------------------------------------------------------------- FFmpeg
Say "FFmpeg"
$LocalFF = Join-Path $Root "ffmpeg"
if (-not (Test-Path "$LocalFF\ffmpeg.exe") -and -not ((Have ffmpeg) -and (Have ffprobe))) {
  if ($HasWinget) { Winget "Gyan.FFmpeg" }
  if (-not ((Have ffmpeg) -and (Have ffprobe))) {
    # sin winget: version "essentials" de gyan.dev (incluye libass y libx264) dentro de la carpeta del proyecto
    $zip = Join-Path $Tmp "ffmpeg.zip"
    Download "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" $zip
    $ex = Join-Path $Tmp "ffmpeg-x"
    if (Test-Path $ex) { Remove-Item -Recurse -Force $ex }
    Expand-Archive -Path $zip -DestinationPath $ex -Force
    $bin = Get-ChildItem -Path $ex -Recurse -Filter ffmpeg.exe | Select-Object -First 1
    if (-not $bin) { Fail "El archivo de FFmpeg descargado no contiene ffmpeg.exe." }
    New-Item -ItemType Directory -Force -Path $LocalFF | Out-Null
    Copy-Item "$($bin.DirectoryName)\*.exe" $LocalFF -Force
  }
}
if (Test-Path "$LocalFF\ffmpeg.exe") { Ok "FFmpeg incluido en la carpeta del proyecto" } else { Ok ((ffmpeg -hide_banner -version | Select-Object -First 1)) }

# ---------------------------------------------------------------- entorno de Python
Say "Instalando el editor (puede tardar 5 a 10 minutos la primera vez)"
$Venv = Join-Path $Root "backend\.venv"
$VPy = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $VPy)) {
  & $PyExe @PyArgs -m venv $Venv
  if (-not (Test-Path $VPy)) { Fail "No se pudo crear el entorno de Python en $Venv." }
}
& $VPy -m pip install --disable-pip-version-check -q --upgrade pip
& $VPy -m pip install --disable-pip-version-check --prefer-binary -q -r (Join-Path $Root "backend\requirements.txt")
if ($LASTEXITCODE -ne 0) { Fail "Fallo la instalacion de las librerias de Python (revisa el mensaje de arriba)." }
Ok "Librerias de Python"

# ---------------------------------------------------------------- interfaz
Say "Interfaz"
if (Test-Path (Join-Path $Root "frontend\dist\index.html")) {
  Ok "Interfaz ya compilada (no hace falta Node.js)"
} elseif (Have npm) {
  Push-Location (Join-Path $Root "frontend"); npm ci --no-audit --no-fund --loglevel=error; npm run build; Pop-Location
  if (-not (Test-Path (Join-Path $Root "frontend\dist\index.html"))) { Fail "No se pudo compilar la interfaz." }
  Ok "Interfaz compilada"
} else {
  Fail "Falta la carpeta frontend\dist. Descarga de nuevo el proyecto completo desde GitHub."
}

# ---------------------------------------------------------------- acceso directo
Say "Creando el acceso directo"
$bat = Join-Path $Root "Iniciar Smart Video Editor.bat"
$lines = @(
  "@echo off",
  "title Smart Video Editor",
  "echo Abriendo Smart Video Editor en tu navegador...",
  "echo No cierres esta ventana mientras uses el editor.",
  "cd /d `"%~dp0backend`"",
  "`".venv\Scripts\python.exe`" -m app",
  "pause"
)
Set-Content -Path $bat -Value $lines -Encoding ASCII
try {
  $lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "Smart Video Editor.lnk"
  $sh = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
  $sh.TargetPath = $bat; $sh.WorkingDirectory = (Join-Path $Root "backend"); $sh.Save()
  Ok "Acceso 'Smart Video Editor' en el escritorio"
} catch { Write-Host "    No se pudo crear el acceso en el escritorio; usa $bat" }

# ---------------------------------------------------------------- verificacion
Say "Verificando (descarga el modelo de transcripcion la primera vez, ~145 MB)"
Push-Location (Join-Path $Root "backend")
& $VPy -m app.selfcheck
$check = $LASTEXITCODE
Pop-Location
Write-Host ""
if ($check -eq 0) {
  Write-Host "LISTO. Abre 'Smart Video Editor' desde el escritorio." -ForegroundColor Green
} else {
  Write-Host "La instalacion termino, pero la verificacion encontro problemas (lineas [FALLA])." -ForegroundColor Yellow
  Write-Host "Envia una captura de esta ventana a quien te ayuda con la instalacion."
}
Read-Host "Presiona Enter para cerrar"
