#!/usr/bin/env python3
"""
REFORMMED Monitor Agent
Collects system metrics every second and sends to the REFORMMED server.
"""

import os, sys, json, time, socket, platform, logging
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

IS_WINDOWS = platform.system() == "Windows"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [AGENT] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger("reformmed-agent")

# ── GPU Detection ──────────────────────────────────────────────────────────────
HAS_NVIDIA = False
try:
    import pynvml
    pynvml.nvmlInit()
    HAS_NVIDIA = True
    log.info("✅ NVIDIA GPU detected")
except Exception:
    pass

def collect_gpu():
    if not HAS_NVIDIA:
        return None
    gpus = []
    try:
        count = pynvml.nvmlDeviceGetCount()
        for i in range(count):
            h    = pynvml.nvmlDeviceGetHandleByIndex(i)
            util = pynvml.nvmlDeviceGetUtilizationRates(h)
            mem  = pynvml.nvmlDeviceGetMemoryInfo(h)
            temp = pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU)
            name = pynvml.nvmlDeviceGetName(h)
            if isinstance(name, bytes):
                name = name.decode()
            gpus.append({
                "index": i, "name": name, "type": "nvidia",
                "gpu_percent": util.gpu,
                "mem_percent": util.memory,
                "mem_used_mb": round(mem.used / 1024**2, 1),
                "mem_total_mb": round(mem.total / 1024**2, 1),
                "temp_c": temp,
            })
    except Exception as e:
        log.debug(f"NVIDIA error: {e}")
    return gpus or None

# ── CPU Temperature ────────────────────────────────────────────────────────────
def get_cpu_temp():
    try:
        temps = psutil.sensors_temperatures()
        if not temps:
            return None
        for name in ["coretemp", "k10temp", "cpu_thermal", "acpitz", "cpu-thermal"]:
            if name in temps:
                vals = [e.current for e in temps[name] if e.current > 0]
                if vals:
                    return round(sum(vals) / len(vals), 1)
        for entries in temps.values():
            vals = [e.current for e in entries if e.current > 0]
            if vals:
                return round(sum(vals) / len(vals), 1)
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
            # Skip loop devices (snap), tmpfs, overlay — not real disks
            if any(x in p.device for x in ["/dev/loop", "tmpfs", "overlay"]):
                continue
            if any(x in p.mountpoint for x in ["/snap/", "/run/snap", "/sys/", "/proc/"]):
                continue
            u = psutil.disk_usage(p.mountpoint)
            parts.append({
                "device": p.device,
                "mountpoint": p.mountpoint,
                "fstype": p.fstype,
                "total_gb": round(u.total / 1024**3, 2),
                "used_gb":  round(u.used  / 1024**3, 2),
                "free_gb":  round(u.free  / 1024**3, 2),
                "percent":  u.percent,
            })
        except PermissionError:
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

# ── Collect All ────────────────────────────────────────────────────────────────
_net_prev  = None
_net_ts    = None

def collect_metrics():
    global _net_prev, _net_ts
    now = datetime.now(timezone.utc)

    cpu_pct   = psutil.cpu_percent(interval=None)
    cpu_cores = psutil.cpu_percent(interval=None, percpu=True)
    cpu_freq  = psutil.cpu_freq()

    ram  = psutil.virtual_memory()
    swap = psutil.swap_memory()

    net_now = psutil.net_io_counters()
    ts_now  = time.time()
    if _net_prev and _net_ts:
        dt       = ts_now - _net_ts or 1
        net_sent = max(0, net_now.bytes_sent   - _net_prev.bytes_sent)  / dt
        net_recv = max(0, net_now.bytes_recv   - _net_prev.bytes_recv)  / dt
        pkt_sent = max(0, net_now.packets_sent - _net_prev.packets_sent)/ dt
        pkt_recv = max(0, net_now.packets_recv - _net_prev.packets_recv)/ dt
    else:
        net_sent = net_recv = pkt_sent = pkt_recv = 0.0
    _net_prev = net_now
    _net_ts   = ts_now

    boot    = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
    uptime  = (now - boot).total_seconds()

    return {
        "system_name":    SYSTEM_NAME,
        "location":       LOCATION,
        "timestamp":      now.isoformat(),
        "cpu_percent":    round(cpu_pct, 1),
        "cpu_per_core":   [round(c, 1) for c in cpu_cores],
        "cpu_freq_mhz":   round(cpu_freq.current if cpu_freq else 0.0, 1),
        "cpu_temp":       get_cpu_temp(),
        "ram_total_gb":   round(ram.total / 1024**3, 2),
        "ram_used_gb":    round(ram.used  / 1024**3, 2),
        "ram_percent":    round(ram.percent, 1),
        "swap_total_gb":  round(swap.total / 1024**3, 2),
        "swap_used_gb":   round(swap.used  / 1024**3, 2),
        "swap_percent":   round(swap.percent, 1),
        "gpu_info":       collect_gpu(),
        "disk_partitions":get_disk_info(),
        "disk_io":        get_disk_io(),
        "net_bytes_sent": round(net_sent, 2),
        "net_bytes_recv": round(net_recv, 2),
        "net_packets_sent": round(pkt_sent, 2),
        "net_packets_recv": round(pkt_recv, 2),
        "public_ip":      get_public_ip(),
        "top_processes":  get_top_processes(),
        "uptime_seconds": uptime,
        "boot_time":      boot.isoformat(),
        "os_version":     platform.platform(),
        "hostname":       socket.gethostname(),
        "status":         "online",
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
                log.warning(f"⚠️ Server unreachable — buffering ({send_queue.qsize()} queued)")

# ── Register ───────────────────────────────────────────────────────────────────
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
            log.warning(f"Register attempt {attempt+1}/60 failed: {e}")
        time.sleep(5)
    return False

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    log.info("=" * 50)
    log.info(f"  REFORMMED Monitor Agent")
    log.info(f"  System   : {SYSTEM_NAME}")
    log.info(f"  Location : {LOCATION}")
    log.info(f"  Server   : {SERVER_URL}")
    log.info(f"  Interval : {SEND_INTERVAL}s")
    log.info("=" * 50)

    # Warm up CPU readings
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
                log.info(f"📊 {sent} sent | CPU: {data['cpu_percent']}% | "
                         f"RAM: {data['ram_percent']}% | Queue: {send_queue.qsize()}")
        except Exception as e:
            log.error(f"Collect error: {e}")
        elapsed = time.time() - loop_start
        time.sleep(max(0, SEND_INTERVAL - elapsed))

if __name__ == "__main__":
    main()
