# core/psutil_lite.py
# Minimal stand-in for the few psutil calls System Stats uses, for platforms
# (Android) where psutil can't be installed. Reads /proc and os.statvfs.
# Android restricts parts of /proc and /sys for normal apps (e.g. /proc/stat
# since Android 8), so some values may be unavailable; those raise
# RuntimeError, which System Stats already shows per-section as "Error: ...".
import os
import collections

_prev_stat = {}


def _read(path):
    try:
        with open(path) as f:
            return f.read()
    except Exception:
        raise RuntimeError("not available on this device")


def cpu_count(logical=True):
    return os.cpu_count() or 1


def cpu_freq():
    best = None
    base = "/sys/devices/system/cpu"
    try:
        for name in os.listdir(base):
            if name.startswith("cpu") and name[3:].isdigit():
                try:
                    with open(f"{base}/{name}/cpufreq/scaling_cur_freq") as f:
                        khz = int(f.read().strip())
                    best = max(best or 0, khz / 1000.0)
                except Exception:
                    pass
    except Exception:
        pass
    if best is None:
        return None
    return collections.namedtuple("freq", "current")(best)


def _parse_stat():
    out = {}
    for line in _read("/proc/stat").splitlines():
        if line.startswith("cpu"):
            p = line.split()
            vals = [int(x) for x in p[1:]]
            idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
            out[p[0]] = (sum(vals), idle)
    if not out:
        raise RuntimeError("not available on this device")
    return out


def cpu_percent(interval=None, percpu=False):
    cur = _parse_stat()
    res = {}
    for k, (tot, idle) in cur.items():
        ptot, pidle = _prev_stat.get(k, (0, 0))
        dt, di = tot - ptot, idle - pidle
        res[k] = 0.0 if dt <= 0 else max(0.0, min(100.0, 100.0 * (dt - di) / dt))
    _prev_stat.clear()
    _prev_stat.update(cur)
    if percpu:
        return [v for k, v in sorted(res.items()) if k != "cpu"]
    return res.get("cpu", 0.0)


def _meminfo():
    d = {}
    for line in _read("/proc/meminfo").splitlines():
        k, _, v = line.partition(":")
        try:
            d[k] = int(v.split()[0]) * 1024
        except Exception:
            pass
    return d


def virtual_memory():
    m = _meminfo()
    total = m.get("MemTotal", 0)
    avail = m.get("MemAvailable", m.get("MemFree", 0))
    used = total - avail
    pct = (100.0 * used / total) if total else 0.0
    return collections.namedtuple("vm", "total available used percent")(
        total, avail, used, pct)


def swap_memory():
    m = _meminfo()
    total = m.get("SwapTotal", 0)
    used = total - m.get("SwapFree", 0)
    return collections.namedtuple("sw", "total used")(total, used)


def disk_partitions(all=False):
    P = collections.namedtuple("part", "mountpoint")
    paths = [p for p in ("/storage/emulated/0", "/data", os.path.expanduser("~"))
             if os.path.isdir(p)]
    seen, out = set(), []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(P(p))
    return out


def disk_usage(path):
    st = os.statvfs(path)
    total = st.f_blocks * st.f_frsize
    free = st.f_bavail * st.f_frsize
    used = total - st.f_bfree * st.f_frsize
    pct = (100.0 * used / total) if total else 0.0
    return collections.namedtuple("du", "total used free percent")(
        total, used, free, pct)


def net_io_counters():
    sent = recv = 0
    for line in _read("/proc/net/dev").splitlines()[2:]:
        name, _, rest = line.partition(":")
        if name.strip() == "lo":
            continue
        f = rest.split()
        recv += int(f[0])
        sent += int(f[8])
    return collections.namedtuple("net", "bytes_sent bytes_recv")(sent, recv)
