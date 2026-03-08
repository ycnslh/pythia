"""
Cross-platform hardware metrics for PYTHIA.

Reads machine resource data from two sources:
- psutil: CPU % (global + per-core), RAM — works everywhere
- Linux sysfs: temperatures, Jetson GPU load — silently absent on other platforms

The public `get_metrics()` function returns only the fields that are actually
available on the current host. Callers should treat all fields beyond the
base set (cpu, ram_*) as optional.
"""

import asyncio
import logging
from pathlib import Path

import psutil

logger = logging.getLogger(__name__)

# Sysfs paths
_THERMAL_BASE = Path("/sys/class/thermal")
_JETSON_GPU_LOAD = Path("/sys/devices/gpu.0/load")

# Canonical key display order.
_THERMAL_KEYS_ORDERED = ["cpu", "gpu", "soc", "tj"]


def _canonical_zone_name(raw_type: str) -> str | None:
    """
    Map a raw thermal zone type string to a canonical display key.

    Uses case-insensitive substring matching so it covers all known variants:
      Jetson Orin:  "BCPU-therm", "MCPU-therm", "GPU-therm",
                    "SOC0-therm", "SOC1-therm", "SOC2-therm", "tj"
      Raspberry Pi: "cpu-thermal"
      Generic:      "cpu", "gpu", ...
    """
    t = raw_type.lower()
    if "cpu" in t:
        return "cpu"
    if "gpu" in t:
        return "gpu"
    if "soc" in t:
        return "soc"
    if t == "tj":
        return "tj"
    return None


def _read_thermal_zones() -> dict[str, float]:
    """
    Read temperatures from /sys/class/thermal/thermal_zone*.

    Returns a dict of canonical_name → °C (rounded to 1 decimal).
    Returns {} on non-Linux systems or if the path does not exist.
    """
    if not _THERMAL_BASE.exists():
        return {}

    # Accumulate raw values; multiple zones can share a canonical key (averaged).
    accumulated: dict[str, list[float]] = {}

    for zone in sorted(_THERMAL_BASE.glob("thermal_zone*")):
        try:
            raw_type = (zone / "type").read_text().strip()
            raw_temp = (zone / "temp").read_text().strip()
            temp_c = int(raw_temp) / 1000.0
        except Exception:
            continue

        # Sanity check: ignore frozen or wildly out-of-range sensors
        if temp_c <= 0 or temp_c >= 120:
            continue

        canonical = _canonical_zone_name(raw_type)
        if canonical is None:
            continue

        accumulated.setdefault(canonical, []).append(temp_c)

    # Average per canonical key, preserve display order
    result: dict[str, float] = {}
    for key in _THERMAL_KEYS_ORDERED:
        values = accumulated.get(key)
        if values:
            result[key] = round(sum(values) / len(values), 1)

    return result


def _read_jetson_gpu() -> float | None:
    """
    Read GPU utilization from the Jetson-specific sysfs node.

    The file contains an integer 0–1000 representing 0.0–100.0%.
    Returns None on any other platform where the file does not exist.
    """
    if not _JETSON_GPU_LOAD.exists():
        return None
    try:
        raw = _JETSON_GPU_LOAD.read_text().strip()
        return round(int(raw) / 10.0, 1)
    except Exception as e:
        logger.debug("Could not read Jetson GPU load: %s", e)
        return None


def _collect_metrics() -> dict:
    """Blocking: gather all hardware metrics. Run in an executor."""
    vm = psutil.virtual_memory()

    disk = psutil.disk_usage("/")

    result: dict = {
        "cpu": psutil.cpu_percent(interval=0.1),
        "cpu_cores": psutil.cpu_percent(interval=None, percpu=True),
        "ram_pct": vm.percent,
        "ram_used_mb": vm.used // (1024 * 1024),
        "ram_total_mb": vm.total // (1024 * 1024),
        "disk_pct": disk.percent,
        "disk_used_gb": round(disk.used / (1024 ** 3), 1),
        "disk_total_gb": round(disk.total / (1024 ** 3), 1),
    }

    gpu = _read_jetson_gpu()
    if gpu is not None:
        result["gpu"] = gpu

    temps = _read_thermal_zones()
    if temps:
        result["temps"] = temps

    return result


async def get_metrics() -> dict:
    """Return hardware metrics dict. Blocking reads run in the default executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _collect_metrics)
