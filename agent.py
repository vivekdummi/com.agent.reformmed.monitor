#!/usr/bin/env python3
import os, sys, time, psutil, requests, json, platform, socket, logging, subprocess
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load .env file
load_dotenv('/opt/reformmed-agent/.env')

logging.basicConfig(level=logging.INFO, format="%(asctime)s [AGENT] %(message)s")
log = logging.getLogger("agent")

# Read config from environment
API_URL = os.getenv("REFORMMED_API_URL", "http://localhost:8000")
API_KEY = os.getenv("REFORMMED_API_SECRET", "")
SYSTEM_NAME = os.getenv("REFORMMED_SYSTEM_NAME", "unknown")
LOCATION = os.getenv("REFORMMED_LOCATION", "unknown")
INTERVAL = int(os.getenv("REFORMMED_INTERVAL", "1"))

# GPU detection
GPU_TYPE = None
HAS_NVIDIA = False
HAS_INTEL = False

try:
    import pynvml
    pynvml.nvmlInit()
    GPU_TYPE = "NVIDIA"
    HAS_NVIDIA = True
    log.info(f"✅ NVIDIA GPU detected ({pynvml.nvmlDeviceGetCount()} device(s))")
except:
    pass

try:
    result = os.popen("lspci | grep -i vga").read().lower()
    if "intel" in result:
        GPU_TYPE = "Intel" if not GPU_TYPE else f"{GPU_TYPE} Intel"
        HAS_INTEL = True
        log.info(f"✅ Intel GPU detected: {result.strip()}")
except:
    pass

log.info("=======================================================")
log.info("  REFORMMED Monitor Agent")
log.info(f"  System   : {SYSTEM_NAME}")
log.info(f"  Location : {LOCATION}")
log.info(f"  Server   : {API_URL}")
log.info(f"  GPU      : {GPU_TYPE or 'None'}")
log.info("=======================================================")

def get_public_ip():
    try:
        return requests.get("https://api.ipify.org", timeout=3).text
    except:
        return "unknown"

def get_intel_gpu_stats():
    """Get Intel GPU stats using intel_gpu_top"""
    try:
        result = subprocess.run(
            ['timeout', '2', 'intel_gpu_top', '-l', '1', '-J'],
            capture_output=True,
            text=True,
            timeout=3
        )
        
        # timeout command returns 124 when it kills the process after 2 seconds
        if result.returncode in [0, 124] and result.stdout:
            output = result.stdout.strip()
            
            # Find the last complete JSON object
            last_brace = output.rfind('}')
            if last_brace == -1:
                return None
            
            # Find matching opening brace
            brace_count = 0
            start_pos = last_brace
            for i in range(last_brace, -1, -1):
                if output[i] == '}':
                    brace_count += 1
                elif output[i] == '{':
                    brace_count -= 1
                    if brace_count == 0:
                        start_pos = i
                        break
            
            last_json = output[start_pos:last_brace+1]
            sample = json.loads(last_json)
            
            engines = sample.get('engines', {})
            total_usage = sum([
                engines.get('Render/3D', {}).get('busy', 0),
                engines.get('Compute', {}).get('busy', 0),
                engines.get('Video', {}).get('busy', 0)
            ])
            
            return {
                'freq_actual': round(sample.get('frequency', {}).get('actual', 0), 2),
                'freq_requested': round(sample.get('frequency', {}).get('requested', 0), 2),
                'power_gpu': round(sample.get('power', {}).get('GPU', 0), 2),
                'power_package': round(sample.get('power', {}).get('Package', 0), 2),
                'usage_total': round(total_usage, 2),
                'render_3d': round(engines.get('Render/3D', {}).get('busy', 0), 2),
                'compute': round(engines.get('Compute', {}).get('busy', 0), 2),
                'video': round(engines.get('Video', {}).get('busy', 0), 2),
                'rc6_idle': round(sample.get('rc6', {}).get('value', 0), 2)
            }
    except Exception as e:
        log.debug(f"Intel GPU stats error: {e}")
    
    return None

def get_gpu_info():
    gpus = []
    
    # NVIDIA GPUs
    if HAS_NVIDIA:
        try:
            import pynvml
            for i in range(pynvml.nvmlDeviceGetCount()):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                gpus.append({
                    "name": pynvml.nvmlDeviceGetName(h),
                    "type": "nvidia",
                    "index": i,
                    "temp_c": pynvml.nvmlDeviceGetTemperature(h, 0),
                    "gpu_percent": pynvml.nvmlDeviceGetUtilizationRates(h).gpu,
                    "mem_percent": pynvml.nvmlDeviceGetUtilizationRates(h).memory,
                    "mem_used_mb": pynvml.nvmlDeviceGetMemoryInfo(h).used // 1024**2,
                    "mem_total_mb": pynvml.nvmlDeviceGetMemoryInfo(h).total // 1024**2
                })
        except Exception as e:
            log.debug(f"NVIDIA GPU error: {e}")
    
    # Intel GPU
    if HAS_INTEL:
        try:
            result = os.popen("lspci | grep -i vga | grep -i intel").read().strip()
            gpu_name = result.split(": ")[1] if ": " in result else result
            
            # Get Intel GPU stats
            intel_stats = get_intel_gpu_stats()
            
            if intel_stats:
                gpus.append({
                    "name": gpu_name,
                    "type": "intel",
                    "index": len(gpus),
                    "temp_c": 0,
                    "gpu_percent": intel_stats['usage_total'],
                    "mem_percent": 0,
                    "mem_used_mb": 0,
                    "mem_total_mb": 0,
                    "freq_actual_mhz": intel_stats['freq_actual'],
                    "freq_requested_mhz": intel_stats['freq_requested'],
                    "power_gpu_w": intel_stats['power_gpu'],
                    "power_package_w": intel_stats['power_package'],
                    "render_3d_percent": intel_stats['render_3d'],
                    "compute_percent": intel_stats['compute'],
                    "video_percent": intel_stats['video'],
                    "rc6_idle_percent": intel_stats['rc6_idle']
                })
            else:
                gpus.append({
                    "name": gpu_name,
                    "type": "intel",
                    "index": len(gpus),
                    "temp_c": 0,
                    "gpu_percent": 0,
                    "mem_percent": 0,
                    "mem_used_mb": 0,
                    "mem_total_mb": 0
                })
        except Exception as e:
            log.debug(f"Intel GPU error: {e}")
    
    return gpus

def collect_metrics():
    cpu_temp = None
    try:
        temps = psutil.sensors_temperatures()
        if "coretemp" in temps:
            cpu_temp = max([t.current for t in temps["coretemp"]])
    except:
        pass
    
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "cpu_per_core": psutil.cpu_percent(interval=0.1, percpu=True),
        "cpu_freq_mhz": psutil.cpu_freq().current if psutil.cpu_freq() else 0,
        "cpu_temp": cpu_temp,
        "ram_total_gb": round(psutil.virtual_memory().total / 1024**3, 2),
        "ram_used_gb": round(psutil.virtual_memory().used / 1024**3, 2),
        "ram_percent": psutil.virtual_memory().percent,
        "swap_total_gb": round(psutil.swap_memory().total / 1024**3, 2),
        "swap_used_gb": round(psutil.swap_memory().used / 1024**3, 2),
        "swap_percent": psutil.swap_memory().percent,
        "gpu_info": get_gpu_info(),
        "disk_partitions": [
            {
                "device": p.device,
                "mountpoint": p.mountpoint,
                "fstype": p.fstype,
                "total_gb": round(psutil.disk_usage(p.mountpoint).total / 1024**3, 2),
                "used_gb": round(psutil.disk_usage(p.mountpoint).used / 1024**3, 2),
                "free_gb": round(psutil.disk_usage(p.mountpoint).free / 1024**3, 2),
                "percent": psutil.disk_usage(p.mountpoint).percent
            }
            for p in psutil.disk_partitions() if p.fstype
        ],
        "disk_io": {
            "read_mb": round(psutil.disk_io_counters().read_bytes / 1024**2, 2),
            "write_mb": round(psutil.disk_io_counters().write_bytes / 1024**2, 2),
            "read_count": psutil.disk_io_counters().read_count,
            "write_count": psutil.disk_io_counters().write_count
        },
        "net_bytes_sent": psutil.net_io_counters().bytes_sent,
        "net_bytes_recv": psutil.net_io_counters().bytes_recv,
        "net_packets_sent": psutil.net_io_counters().packets_sent,
        "net_packets_recv": psutil.net_io_counters().packets_recv,
        "top_processes": [
            {
                "pid": p.pid,
                "name": p.name(),
                "cpu_percent": p.cpu_percent(),
                "mem_percent": round(p.memory_percent(), 2),
                "status": p.status()
            }
            for p in sorted(psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']),
                          key=lambda x: x.cpu_percent(), reverse=True)[:20]
        ],
        "uptime_seconds": round(time.time() - psutil.boot_time(), 2),
        "boot_time": datetime.fromtimestamp(psutil.boot_time(), timezone.utc).isoformat(),
        "public_ip": get_public_ip(),
        "os_version": platform.platform(),
        "hostname": socket.gethostname(),
        "status": "online"
    }

def register():
    for attempt in range(1, 61):
        try:
            resp = requests.post(
                f"{API_URL}/register",
                json={
                    "system_name": SYSTEM_NAME,
                    "location": LOCATION,
                    "os_type": "linux",
                    "hostname": socket.gethostname(),
                    "public_ip": get_public_ip()
                },
                headers={"X-API-Key": API_KEY},
                timeout=5
            )
            if resp.status_code == 200:
                table_name = resp.json()["table_name"]
                log.info(f"✅ Registered as: {table_name}")
                return table_name
            log.error(f"Register failed: {resp.status_code} {resp.text}")
        except Exception as e:
            log.error(f"Register attempt {attempt}/60: {e}")
        time.sleep(5)
    sys.exit(1)

def main():
    table_name = register()
    count = 0
    
    while True:
        try:
            data = collect_metrics()
            data["table_name"] = table_name
            
            resp = requests.post(
                f"{API_URL}/metrics",
                json=data,
                headers={"X-API-Key": API_KEY},
                timeout=5
            )
            
            if resp.status_code == 200:
                count += 1
                gpu_count = len(data['gpu_info'])
                gpu_usage = data['gpu_info'][0]['gpu_percent'] if gpu_count > 0 else 0
                log.info(f"📊 {count} sent | CPU: {data['cpu_percent']}% | RAM: {data['ram_percent']}% | GPU: {gpu_usage}% ({gpu_count}) | Temp: {data['cpu_temp']}°C")
            else:
                log.error(f"Send failed: {resp.status_code}")
        except Exception as e:
            log.error(f"Send error: {e}")
        
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
