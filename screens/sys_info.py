# screens/sys_info.py — shared system-info helpers.
#
# Pulled out of system_stats_screen.py so the overlay window
# (_overlay_app.py, a separate process) can show the same GPU info
# without duplicating the detection logic.

import sys, os, re, subprocess

try:
    import GPUtil
    HAS_GPUTIL = True
except ImportError:
    HAS_GPUTIL = False

try:
    from ping3 import ping as ping3_ping
    HAS_PING3 = True
except ImportError:
    HAS_PING3 = False


def gpu_info_lines():
    """Full multi-line GPU info (name/load/VRAM/temp), used by the System
    Stats screen's GPU panel."""
    lines = []
    if HAS_GPUTIL:
        try:
            for g in GPUtil.getGPUs():
                lines += [f"[b]{g.name}[/b]",
                           f"  Load: {g.load*100:.1f}%",
                           f"  VRAM: {g.memoryUsed:.0f}/{g.memoryTotal:.0f} MB",
                           f"  Temp: {g.temperature} C"]
            return lines
        except Exception:
            pass
    try:
        out = subprocess.check_output(
            ["nvidia-smi",
             "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            timeout=3, stderr=subprocess.DEVNULL
        ).decode(errors="replace").strip()
        for row in out.splitlines():
            p = [x.strip() for x in row.split(",")]
            if len(p) >= 5:
                lines += [f"[b]{p[0]}[/b]",
                           f"  Load: {p[1]}%",
                           f"  VRAM: {p[2]}/{p[3]} MB",
                           f"  Temp: {p[4]} C"]
        if lines:
            return lines
    except Exception:
        pass
    if sys.platform.startswith("linux"):
        try:
            drm = "/sys/class/drm"
            for card in sorted(os.listdir(drm)):
                gp = os.path.join(drm, card, "device", "gpu_busy_percent")
                if os.path.exists(gp):
                    util = open(gp).read().strip()
                    lines += [f"[b]{card}[/b]", f"  Load: {util}%"]
            if lines:
                return lines
        except Exception:
            pass
    lines.append("GPU info not available")
    return lines


def gpu_summary_line():
    """One compact line for tight spaces (the overlay window): first GPU's
    name + load%, or a short status string if unavailable."""
    if HAS_GPUTIL:
        try:
            gpus = GPUtil.getGPUs()
            if gpus:
                g = gpus[0]
                return f"{g.name}: {g.load*100:.0f}%"
        except Exception:
            pass
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,utilization.gpu",
             "--format=csv,noheader,nounits"],
            timeout=2, stderr=subprocess.DEVNULL
        ).decode(errors="replace").strip().splitlines()
        if out:
            p = [x.strip() for x in out[0].split(",")]
            if len(p) >= 2:
                return f"{p[0]}: {p[1]}%"
    except Exception:
        pass
    if sys.platform.startswith("linux"):
        try:
            drm = "/sys/class/drm"
            for card in sorted(os.listdir(drm)):
                gp = os.path.join(drm, card, "device", "gpu_busy_percent")
                if os.path.exists(gp):
                    return f"{card}: {open(gp).read().strip()}%"
        except Exception:
            pass
    return "N/A"


def do_ping(host) -> float:
    if HAS_PING3:
        try:
            r = ping3_ping(host, timeout=2, unit="ms")
            if r is not None and r is not False:
                return float(r)
        except Exception:
            pass
    try:
        cmd = (["ping", "-n", "1", "-w", "2000", host]
               if sys.platform.startswith("win")
               else ["ping", "-c", "1", "-W", "2", host])
        out = subprocess.check_output(
            cmd, stderr=subprocess.DEVNULL, timeout=4
        ).decode(errors="replace")
        m = re.search(r"time[=<](\d+\.?\d*)\s*ms", out)
        if m:
            return float(m.group(1))
    except Exception:
        pass
    return -1.0
