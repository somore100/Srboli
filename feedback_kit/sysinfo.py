"""Opt-in system information. Only hardware/OS basics: no username, hostname, serial numbers, IP/MAC or file paths."""
import os
import platform
import subprocess
import sys


def _run(cmd, timeout=4):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _cpu():
    sysname = platform.system()
    try:
        if sysname == "Linux":
            with open("/proc/cpuinfo") as fh:
                for line in fh:
                    if line.lower().startswith(("model name", "hardware", "processor\t: ") ) and ":" in line and not line.split(":")[1].strip().isdigit():
                        return line.split(":", 1)[1].strip()
        if sysname == "Darwin":
            return _run(["sysctl", "-n", "machdep.cpu.brand_string"]) or platform.processor()
        if sysname == "Windows":
            return os.environ.get("PROCESSOR_IDENTIFIER", "") or platform.processor()
    except OSError:
        pass
    return platform.processor() or "unknown"


def _gpu():
    sysname = platform.system()
    names = []
    if sysname == "Linux":
        for line in _run(["lspci"]).splitlines():
            if any(k in line for k in ("VGA compatible", "3D controller", "Display controller")):
                names.append(line.split(": ", 1)[-1].strip())
        if not names:                      # no lspci: fall back to the PCI vendor:device ids of the display adapters
            try:
                import glob
                for d in sorted(glob.glob("/sys/class/drm/card[0-9]/device")):
                    ids = [open(os.path.join(d, k)).read().strip()[2:] for k in ("vendor", "device")]
                    names.append("PCI " + ":".join(ids))
            except OSError:
                pass
    elif sysname == "Windows":
        out = _run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_VideoController).Name"], timeout=8)
        names = [l.strip() for l in out.splitlines() if l.strip()]
    elif sysname == "Darwin":
        for line in _run(["system_profiler", "SPDisplaysDataType"], timeout=8).splitlines():
            if "Chipset Model" in line:
                names.append(line.split(":", 1)[1].strip())
    return ", ".join(names) or "unknown"


def _ram_gb():
    sysname = platform.system()
    try:
        if sysname == "Linux":
            with open("/proc/meminfo") as fh:
                for line in fh:
                    if line.startswith("MemTotal"):
                        return round(int(line.split()[1]) / 1048576, 1)
        if sysname == "Darwin":
            return round(int(_run(["sysctl", "-n", "hw.memsize"])) / 2 ** 30, 1)
        if sysname == "Windows":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("a", ctypes.c_ulonglong),
                            ("b", ctypes.c_ulonglong), ("c", ctypes.c_ulonglong), ("d", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]
            m = MS()
            m.l = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return round(m.total / 2 ** 30, 1)
    except (OSError, ValueError, AttributeError):
        pass
    return None


def collect_system_info(app_version=""):
    """Dict of what will be sent. Call it only after the user has opted in."""
    info = {"OS": f"{platform.system()} {platform.release()} ({platform.version()[:80]})",
            "Architecture": platform.machine() or "unknown",
            "CPU": _cpu(), "CPU cores": os.cpu_count() or "?", "GPU": _gpu(),
            "RAM": f"{_ram_gb()} GB" if _ram_gb() else "unknown",
            "Python": platform.python_version()}
    try:
        import pygame
        info["pygame"] = pygame.version.ver
    except Exception:
        pass
    if app_version:
        info["App version"] = app_version
    return info


def format_system_info(info):
    return [f"{k}: {v}" for k, v in info.items()]
