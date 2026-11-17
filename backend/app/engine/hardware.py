"""Perfil del equipo para elegir ajustes rápidos automáticamente (modelo Whisper, velocidad de exportación)."""
from __future__ import annotations

import ctypes
import os
import platform
import subprocess
from functools import lru_cache


def _ram_gb() -> float:
    try:
        if os.name == "nt":
            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            ms = MS()
            ms.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))  # type: ignore[attr-defined]
            return ms.ullTotalPhys / 2**30
        if platform.system() == "Darwin":
            return int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout) / 2**30
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / 2**20
    except Exception:  # noqa: BLE001
        pass
    return 8.0


def _avx2() -> bool:
    try:
        if os.name == "nt":
            return bool(ctypes.windll.kernel32.IsProcessorFeaturePresent(40))  # type: ignore[attr-defined]
        if platform.system() == "Darwin":
            out = subprocess.run(["sysctl", "-n", "machdep.cpu.leaf7_features"], capture_output=True, text=True).stdout
            return "AVX2" in out or platform.machine() == "arm64"
        with open("/proc/cpuinfo") as f:
            return " avx2" in f.read()
    except Exception:  # noqa: BLE001
        return True


@lru_cache(maxsize=1)
def profile() -> dict:
    threads = os.cpu_count() or 2
    ram = round(_ram_gb(), 1)
    avx2 = _avx2()
    modest = threads <= 4 or ram < 8 or not avx2
    return {
        "threads": threads,
        "ram_gb": ram,
        "avx2": avx2,
        "tier": "modesto" if modest else "normal",
        # base transcribe bien en español; tiny comete muchos errores y solo se usa con muy poca RAM
        "whisper_model": "tiny" if ram < 4 else "base",
        # veryfast codifica ~2–3× más rápido que medium con archivos algo más pesados
        "export_preset": "veryfast" if modest else "faster",
        "proxy_height": 540 if modest else 720,
    }
