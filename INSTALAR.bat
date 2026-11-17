@echo off
title Instalador de Smart Video Editor
echo Instalando Smart Video Editor. No cierres esta ventana.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\instalar.ps1"
