import os
import multiprocessing

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None


def core_count() -> int:
    try:
        return multiprocessing.cpu_count()
    except Exception:
        return int(os.environ.get("CPU_CORES", "4"))


def threads_for_limit(limit_fraction: float = 0.8) -> int:
    cores = core_count()
    return max(1, int(cores * limit_fraction))


def per_core_usage():
    """Return per-core CPU usage list if psutil is available, else empty list."""
    if psutil is None:
        return []
    try:
        return psutil.cpu_percent(interval=0.5, percpu=True)
    except Exception:
        return []
