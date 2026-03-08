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

# Thermal zone type names → canonical short keys for display.
# Multiple raw names can map to the same key (they are averaged).
_THERMAL_NAME_MAP: dict[str, str] = {
    "cpu-thermal": "cpu",
    "cpu": "cpu",
    "CPU": "cpu",
    "gpu": "gpu",
    "GPU": "gpu",
    "soc0": "soc",
    "soc1": "soc",
    "soc2": "soc",
    "tj": "tj",
}

# Only surface these canonical keys (in this display order).
_THERMAL_KEYS_ORDERED = ["cpu", "gpu", "soc", "tj"]


def _read_thermal_zones() -> dict[str, float]:
    """
    Read temperatures from /sys/class/thermal/thermal_zone*.

    Returns a dict of canonical_name → °C (rounded to 1 decimal).
    Returns {} on non-Linux systems or if the path does not exist.
    """
    if not _THERMAL_BASE.exists():
        return {}

    # Accumulate raw values; some keys may appear multiple times (e.g. soc0/soc1/soc2).
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

        canonical = _THERMAL_NAME_MAP.get(raw_type)
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

    result: dict = {
        "cpu": psutil.cpu_percent(interval=0.1),
        "cpu_cores": psutil.cpu_percent(interval=None, percpu=True),
        "ram_pct": vm.percent,
        "ram_used_mb": vm.used // (1024 * 1024),
        "ram_total_mb": vm.total // (1024 * 1024),
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
