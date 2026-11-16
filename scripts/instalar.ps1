# Instalador para Windows 10/11. Uso, en PowerShell desde la carpeta del proyecto:
#   powershell -ExecutionPolicy Bypass -File scripts\instalar.ps1
# Verifica Python 3.10+, Node 18+ y FFmpeg; instala lo que falte con winget, prepara el entorno de
# Python, compila la interfaz y crea "Iniciar Smart Video Editor.bat" y un acceso en el escritorio.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
function Say($m) { Write-Host "`n> $m" -ForegroundColor Magenta }
function Have($c) { [bool](Get-Command $c -ErrorAction SilentlyContinue) }
function Refresh-Path {
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}
function WingetInstall($id) {
  if (-not (Have winget)) { throw "Falta winget (App Installer de Microsoft Store). Instálalo o instala $id a mano." }
  winget install --id $id -e --accept-source-agreements --accept-package-agreements --silent
  Refresh-Path
}

Say "Revisando Python 3.10 o superior"
$py = $null
foreach ($c in @("py -3.12", "py -3.11", "py -3.10", "python")) {
  try {
    $exe, $arg = $c.Split(" ", 2)
    & $exe $arg -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) { $py = $c; break }
  } catch {}
}
if (-not $py) { WingetInstall "Python.Python.3.12"; $py = "py -3.12" }
$pyExe, $pyArg = $py.Split(" ", 2)
Write-Host "OK: $(& $pyExe $pyArg --version)"

Say "Revisando Node.js 18 o superior"
if (-not (Have node) -or [int](node -p "process.versions.node.split('.')[0]") -lt 18) { WingetInstall "OpenJS.NodeJS.LTS" }
Write-Host "OK: node $(node --version)"

Say "Revisando FFmpeg"
if (-not (Have ffmpeg) -or -not (Have ffprobe)) { WingetInstall "Gyan.FFmpeg" }
Write-Host "OK: $((ffmpeg -hide_banner -version)[0])"

Say "Creando entorno de Python (backend\.venv)"
if (-not (Test-Path "backend\.venv")) { & $pyExe $pyArg -m venv backend\.venv }
& backend\.venv\Scripts\python.exe -m pip install -q --upgrade pip
& backend\.venv\Scripts\python.exe -m pip install -q -r backend\requirements.txt

Say "Compilando la interfaz"
Push-Location frontend
npm ci --no-audit --no-fund --loglevel=error
npm run build --silent
Pop-Location

Say "Creando el lanzador"
$bat = Join-Path $Root "Iniciar Smart Video Editor.bat"
"@echo off`r`ncd /d `"$Root\backend`"`r`n.venv\Scripts\python.exe -m app`r`npause" | Set-Content -Encoding ASCII $bat
$lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "Smart Video Editor.lnk"
$sh = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$sh.TargetPath = $bat; $sh.WorkingDirectory = "$Root\backend"; $sh.Save()

Say "Listo"
Write-Host "Abre el editor con el acceso 'Smart Video Editor' del escritorio."
Write-Host "La primera transcripcion descarga el modelo de Whisper (~145 MB)."
