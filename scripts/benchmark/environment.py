"""Captura del entorno donde corre el banco (equipo, SO, Docker, versiones y reglas usadas)."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SIDDHI_APP = ROOT / "cep" / "siddhi" / "CargoMonitoring.siddhi"


def _run(*command: str) -> str | None:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)  # noqa: S603
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _cpu_name() -> str:
    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    return platform.processor() or "desconocido"


def _ram_bytes() -> int | None:
    if sys.platform == "win32":

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):  # type: ignore[attr-defined]
            return int(status.ullTotalPhys)
        return None
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    return None


def _docker() -> dict[str, Any]:
    info_raw = _run("docker", "info", "--format", "{{json .}}")
    info = json.loads(info_raw) if info_raw else {}
    return {
        "server_version": info.get("ServerVersion"),
        "client_version": _run("docker", "version", "--format", "{{.Client.Version}}"),
        "compose_version": _run("docker", "compose", "version", "--short"),
        "vm_os": info.get("OperatingSystem"),
        "vm_kernel": info.get("KernelVersion"),
        "vm_cpus": info.get("NCPU"),
        "vm_memory_bytes": info.get("MemTotal"),
    }


def _container(name: str) -> dict[str, Any]:
    raw = _run("docker", "inspect", "--format", "{{json .Config.Image}} {{json .Image}}", name)
    if not raw:
        return {"name": name, "found": False}
    image, image_id = (json.loads(part) for part in raw.split(" ", 1))
    return {"name": name, "found": True, "image": image, "image_id": image_id}


def capture(cep_container: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    ram = _ram_bytes()
    return {
        "captured_at": datetime.now(UTC).isoformat(),
        "host": {
            "os": f"{platform.system()} {platform.release()} ({platform.version()})",
            "machine": platform.machine(),
            "cpu": _cpu_name(),
            "logical_cpus": os.cpu_count(),
            "ram_gb": round(ram / 1024**3, 2) if ram else None,
            "python": platform.python_version(),
        },
        "docker": _docker(),
        "cep_container": _container(cep_container),
        "siddhi_app": {
            "path": str(SIDDHI_APP.relative_to(ROOT)),
            "sha256": hashlib.sha256(SIDDHI_APP.read_bytes()).hexdigest(),
        },
        **(extra or {}),
    }
