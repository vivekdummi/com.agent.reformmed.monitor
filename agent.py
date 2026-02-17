#!/usr/bin/env python3
"""
REFORMMED Monitor Agent — Full GPU Support (NVIDIA + Intel + AMD)
"""
import os, sys, json, time, socket, platform, logging, subprocess
import threading, queue, urllib.request
from datetime import datetime, timezone
from typing import Optional

import psutil
import requests

SERVER_URL    = os.getenv("REFORMMED_SERVER_URL", "http://localhost:8000")
API_KEY       = os.getenv("REFORMMED_API_KEY", "reformmed-secret-key")
SYSTEM_NAME   = os.getenv("REFORMMED_SYSTEM_NAME", "unknown")
LOCATION      = os.getenv("REFORMMED_LOCATION", "unknown")
SEND_INTERVAL = float(os.getenv("REFORMMED_INTERVAL", "1.0"))
IS_WINDOWS    = platform.system() == "Windows"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [AGENT] %(message)s")
log = logging.getLogger("reformmed-agent")

# ── NVIDIA GPU ─────────────────────────────────────────────────────────────────
HAS_NVIDIA = False
try:
    import pynvml
    pynvml.nvmlInit()
    HAS_NVIDIA = True
    log.info(f"✅ NVIDIA GPU detected ({pynvml.nvmlDeviceGetCount()} device(s))")
except Exception:
    pass

# ── Intel GPU detection ────────────────────────────────────────────────────────
def detect_intel_gpu():
    """Detect Intel iGPU via lspci or /sys/class/drm"""
    try:
        result = subprocess.run(
            ["lspci"], capture_output=True, text=True, timeout=3
        )
        for line in result.stdout.splitlines():
            if "VGA" in line or "Display" in line or "3D" in line:
                if "Intel" in line:
                    return line.split(":")[-1].strip()
    except Exception:
        pass
    try:
        vendor = open("/sys/class/drm/card0/device/vendor").read().strip()
        if vendor == "0x8086":  # Intel vendor ID
            device = open("/sys/class/drm/card0/device/uevent").read()
            for line in device.splitlines():
                if "DRIVER=" in line:
                    return f"Intel iGPU ({line.split('=')[1]})"
            return "Intel iGPU"
    except Exception:
        pass
    return None

# ── AMD GPU detection ──────────────────────────────────────────────────────────
def detect_amd_gpu():
    try:
        result = subprocess.run(
            ["lspci"], capture_output=True, text=True, timeout=3
        )
        for line in result.stdout.splitlines():
            if ("VGA" in line or "Display" in line) and "AMD" in line:
                return line.split(":")[-1].strip()
    except Exception:
        pass
    return None

INTEL_GPU_NAME = detect_intel_gpu()
AMD_GPU_NAME   = detect_amd_gpu()

if INTEL_GPU_NAME:
    log.info(f"✅ Intel GPU detected: {INTEL_GPU_NAME}")
if AMD_GPU_NAME:
    log.info(f"✅ AMD GPU detected: {AMD_GPU_NAME}")
if not HAS_NVIDIA and not INTEL_GPU_NAME and not AMD_GPU_NAME:
    log.info("ℹ️  No GPU detected — GPU metrics will be null")

# ── Intel GPU metrics via intel_gpu_top ────────────────────────────────────────
def get_intel_gpu_metrics():
    """Try to get Intel GPU usage % via intel_gpu_top or sysfs"""
    # Method 1: intel_gpu_top (needs root or sudo)
    try:
        result = subprocess.run(
            ["intel_gpu_top", "-J", "-s", "500"],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            data = json.loads(result.stdout.split("\n")[1])
            engines = data.get("engines", {})
            render = engines.get("Render/3D", {})
            usage  = render.get("busy", 0)
            return round(usage, 1)
    except Exception:
        pass

    # Method 2: sysfs GPU frequency as proxy
    try:
        freq_path = "/sys/class/drm/card0/gt_cur_freq_mhz"
        max_path  = "/sys/class/drm/card0/gt_max_freq_mhz"
        cur  = int(open(freq_path).read().strip())
        maxi = int(open(max_path).read().strip())
        if maxi > 0:
            return round((cur / maxi) * 100, 1)
    except Exception:
        pass
    return 0.0

# ── AMD GPU metrics via rocm-smi ───────────────────────────────────────────────
def get_amd_gpu_metrics():
    try:
        result = subprocess.run(
            ["rocm-smi", "--showuse", "--showtemp", "--showmemuse", "--json"],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            card = list(data.values())[0]
            return {
                "gpu_percent": float(card.get("GPU use (%)", 0)),
                "temp_c":      float(card.get("Temperature (Sensor edge) (C)", 0)),
                "mem_percent": float(card.get("GPU memory use (%)", 0)),
            }
    except Exception:
        pass
    return {"gpu_percent": 0.0, "temp_c": 0.0, "mem_percent": 0.0}

# ── Collect all GPU info ───────────────────────────────────────────────────────
def collect_gpu():
    gpus = []

    # NVIDIA
    if HAS_NVIDIA:
        try:
            for i in range(pynvml.nvmlDeviceGetCount()):
                h    = pynvml.nvmlDeviceGetHandleByIndex(i)
                util = pynvml.nvmlDeviceGetUtilizationRates(h)
                mem  = pynvml.nvmlDeviceGetMemoryInfo(h)
                temp = pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU)
                name = pynvml.nvmlDeviceGetName(h)
                if isinstance(name, bytes):
                    name = name.decode()
                gpus.append({
                    "index":       i,
                    "name":        name,
                    "type":        "nvidia",
                    "gpu_percent": util.gpu,
                    "mem_percent": round(mem.used / mem.total * 100, 1) if mem.total > 0 else 0,
                    "mem_used_mb": round(mem.used  / 1024**2, 1),
                    "mem_total_mb":round(mem.total / 1024**2, 1),
                    "temp_c":      temp,
                })
        except Exception as e:
            log.debug(f"NVIDIA read error: {e}")

    # Intel iGPU
    if INTEL_GPU_NAME:
        usage = get_intel_gpu_metrics()
        # Get VRAM from /proc/meminfo MemAvailable as proxy
        try:
            meminfo = open("/proc/meminfo").read()
            total_kb = int([l for l in meminfo.splitlines() if "MemTotal" in l][0].split()[1])
            avail_kb = int([l for l in meminfo.splitlines() if "MemAvailable" in l][0].split()[1])
            used_mb  = round((total_kb - avail_kb) / 1024, 1)
            total_mb = round(total_kb / 1024, 1)
            mem_pct  = round(used_mb / total_mb * 100, 1) if total_mb > 0 else 0
        except Exception:
            used_mb = total_mb = mem_pct = 0

        # CPU temp as GPU temp proxy for integrated graphics
        cpu_temp = get_cpu_temp() or 0
        gpus.append({
            "index":       0,
            "name":        INTEL_GPU_NAME,
            "type":        "intel",
            "gpu_percent": usage,
            "mem_percent": mem_pct,
            "mem_used_mb": used_mb,
            "mem_total_mb":total_mb,
            "temp_c":      cpu_temp,
        })

    # AMD
    if AMD_GPU_NAME:
        metrics = get_amd_gpu_metrics()
        gpus.append({
            "index":       0,
            "name":        AMD_GPU_NAME,
            "type":        "amd",
            "gpu_percent": metrics["gpu_percent"],
            "mem_percent": metrics["mem_percent"],
            "mem_used_mb": 0,
            "mem_total_mb":0,
            "temp_c":      metrics["temp_c"],
        })

    return gpus if gpus else None

# ── CPU Temperature ────────────────────────────────────────────────────────────
def get_cpu_temp():
    try:
        temps = psutil.sensors_temperatures()
        if not temps:
            return None
        for name in ["coretemp","k10temp","cpu_thermal","acpitz","cpu-thermal"]:
            if name in temps:
                vals = [e.current for e in temps[name] if e.current > 0]
                if vals:
                    return round(sum(vals)/len(vals), 1)
        for entries in temps.values():
            vals = [e.current for e in entries if e.current > 0]
            if vals:
                return round(sum(vals)/len(vals), 1)
    except Exception:
        pass
    return None

# ── Public IP (cached 60s) ─────────────────────────────────────────────────────
_ip_cache = {"ip": None, "ts": 0}
def get_public_ip():
    now = time.time()
    if now - _ip_cache["ts"] < 60:
        return _ip_cache["ip"]
    try:
        ip = urllib.request.urlopen("https://api.ipify.org", timeout=5).read().decode().strip()
        _ip_cache.update({"ip": ip, "ts": now})
        return ip
    except Exception:
        return _ip_cache["ip"]

# ── Disk ───────────────────────────────────────────────────────────────────────
def get_disk_info():
    parts = []
    for p in psutil.disk_partitions(all=False):
        try:
            # Skip snap/loop/tmpfs/overlay — not real disks
            if any(x in p.device    for x in ["/dev/loop","tmpfs","overlay","devtmpfs"]):
                continue
            if any(x in p.mountpoint for x in ["/snap/","/run/snap","/sys/","/proc/"]):
                continue
            if p.fstype in ["squashfs","tmpfs","devtmpfs","overlay"]:
                continue
            u = psutil.disk_usage(p.mountpoint)
            parts.append({
                "device":     p.device,
                "mountpoint": p.mountpoint,
                "fstype":     p.fstype,
                "total_gb":   round(u.total / 1024**3, 2),
                "used_gb":    round(u.used  / 1024**3, 2),
                "free_gb":    round(u.free  / 1024**3, 2),
                "percent":    u.percent,
            })
        except (PermissionError, OSError):
            continue
    return parts

def get_disk_io():
    try:
        io = psutil.disk_io_counters()
        if io:
            return {
                "read_mb":    round(io.read_bytes  / 1024**2, 2),
                "write_mb":   round(io.write_bytes / 1024**2, 2),
                "read_count":  io.read_count,
                "write_count": io.write_count,
            }
    except Exception:
        pass
    return None

# ── Top Processes ──────────────────────────────────────────────────────────────
def get_top_processes(n=10):
    procs = []
    for p in psutil.process_iter(["pid","name","cpu_percent","memory_percent","status"]):
        try:
            procs.append({
                "pid":         p.info["pid"],
                "name":        p.info["name"],
                "cpu_percent": round(p.info["cpu_percent"] or 0, 1),
                "mem_percent": round(p.info["memory_percent"] or 0, 2),
                "status":      p.info["status"],
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    procs.sort(key=lambda x: x["cpu_percent"], reverse=True)
    return procs[:n]

# ── Network ────────────────────────────────────────────────────────────────────
_net_prev = None
_net_ts   = None

def collect_metrics():
    global _net_prev, _net_ts
    now = datetime.now(timezone.utc)

    cpu_pct   = psutil.cpu_percent(interval=None)
    cpu_cores = psutil.cpu_percent(interval=None, percpu=True)
    cpu_freq  = psutil.cpu_freq()
    ram       = psutil.virtual_memory()
    swap      = psutil.swap_memory()

    net_now = psutil.net_io_counters()
    ts_now  = time.time()
    if _net_prev and _net_ts:
        dt       = ts_now - _net_ts or 1
        net_sent = max(0, net_now.bytes_sent   - _net_prev.bytes_sent)   / dt
        net_recv = max(0, net_now.bytes_recv   - _net_prev.bytes_recv)   / dt
        pkt_sent = max(0, net_now.packets_sent - _net_prev.packets_sent) / dt
        pkt_recv = max(0, net_now.packets_recv - _net_prev.packets_recv) / dt
    else:
        net_sent = net_recv = pkt_sent = pkt_recv = 0.0
    _net_prev = net_now
    _net_ts   = ts_now

    boot   = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
    uptime = (now - boot).total_seconds()

    return {
        "system_name":     SYSTEM_NAME,
        "location":        LOCATION,
        "timestamp":       now.isoformat(),
        "cpu_percent":     round(cpu_pct, 1),
        "cpu_per_core":    [round(c, 1) for c in cpu_cores],
        "cpu_freq_mhz":    round(cpu_freq.current if cpu_freq else 0.0, 1),
        "cpu_temp":        get_cpu_temp(),
        "ram_total_gb":    round(ram.total / 1024**3, 2),
        "ram_used_gb":     round(ram.used  / 1024**3, 2),
        "ram_percent":     round(ram.percent, 1),
        "swap_total_gb":   round(swap.total / 1024**3, 2),
        "swap_used_gb":    round(swap.used  / 1024**3, 2),
        "swap_percent":    round(swap.percent, 1),
        "gpu_info":        collect_gpu(),
        "disk_partitions": get_disk_info(),
        "disk_io":         get_disk_io(),
        "net_bytes_sent":  round(net_sent, 2),
        "net_bytes_recv":  round(net_recv, 2),
        "net_packets_sent":round(pkt_sent, 2),
        "net_packets_recv":round(pkt_recv, 2),
        "public_ip":       get_public_ip(),
        "top_processes":   get_top_processes(),
        "uptime_seconds":  uptime,
        "boot_time":       boot.isoformat(),
        "os_version":      platform.platform(),
        "hostname":        socket.gethostname(),
        "status":          "online",
    }

# ── Send queue ─────────────────────────────────────────────────────────────────
HEADERS    = {"Content-Type": "application/json", "X-Api-Key": API_KEY}
SESSION    = requests.Session()
send_queue = queue.Queue(maxsize=300)
failed_count = 0

def send_metrics(payload):
    try:
        r = SESSION.post(f"{SERVER_URL}/metrics", json=payload, headers=HEADERS, timeout=5)
        return r.status_code == 200
    except Exception as e:
        log.debug(f"Send failed: {e}")
        return False

def sender_thread():
    global failed_count
    while True:
        payload = send_queue.get()
        if payload is None:
            break
        ok = send_metrics(payload)
        if ok:
            if failed_count > 0:
                log.info("✅ Connection restored")
            failed_count = 0
        else:
            failed_count += 1
            if failed_count % 10 == 1:
                log.warning(f"⚠️  Server unreachable — buffering ({send_queue.qsize()} queued)")

def register():
    payload = {
        "system_name": SYSTEM_NAME,
        "location":    LOCATION,
        "os_type":     "windows" if IS_WINDOWS else "linux",
        "hostname":    socket.gethostname(),
        "public_ip":   get_public_ip(),
    }
    for attempt in range(60):
        try:
            r = SESSION.post(f"{SERVER_URL}/register", json=payload, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                log.info(f"✅ Registered → table: {r.json().get('table_name')}")
                return True
        except Exception as e:
            log.warning(f"Register attempt {attempt+1}/60: {e}")
        time.sleep(5)
    return False

def main():
    log.info("=" * 55)
    log.info(f"  REFORMMED Monitor Agent")
    log.info(f"  System   : {SYSTEM_NAME}")
    log.info(f"  Location : {LOCATION}")
    log.info(f"  Server   : {SERVER_URL}")
    log.info(f"  GPU      : {'NVIDIA' if HAS_NVIDIA else ''} {'Intel' if INTEL_GPU_NAME else ''} {'AMD' if AMD_GPU_NAME else ''} {'None' if not HAS_NVIDIA and not INTEL_GPU_NAME and not AMD_GPU_NAME else ''}")
    log.info("=" * 55)

    psutil.cpu_percent(interval=0.1)
    psutil.cpu_percent(interval=None, percpu=True)

    if not register():
        log.error("❌ Registration failed — exiting")
        sys.exit(1)

    t = threading.Thread(target=sender_thread, daemon=True)
    t.start()

    log.info("📡 Sending metrics every second...")
    sent = 0
    while True:
        loop_start = time.time()
        try:
            data = collect_metrics()
            if not send_queue.full():
                send_queue.put(data)
            sent += 1
            if sent % 30 == 0:
                gpu_str = ""
                if data["gpu_info"]:
                    g = data["gpu_info"][0]
                    gpu_str = f" | GPU({g['type']}): {g['gpu_percent']}%"
                log.info(f"📊 {sent} sent | CPU: {data['cpu_percent']}% | RAM: {data['ram_percent']}%{gpu_str}")
        except Exception as e:
            log.error(f"Collect error: {e}")
        elapsed = time.time() - loop_start
        time.sleep(max(0, SEND_INTERVAL - elapsed))

if __name__ == "__main__":
    main()
