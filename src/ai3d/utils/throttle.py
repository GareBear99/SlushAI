import os
import signal
import time
from dataclasses import dataclass

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None


@dataclass
class CPUThrottleConfig:
    target_fraction: float = 0.80  # 80% of available CPU across all cores
    interval: float = 2.0          # sample/ping every 2 seconds
    smoothing: float = 0.5         # EMA smoothing for usage


class CPUThrottler:
    """
    Best-effort CPU limiter using SIGSTOP/SIGCONT duty cycling.
    - Does NOT kill the process; it yields time when usage exceeds target.
    - Works cross-platform where signals are supported (macOS, Linux).
    - Requires psutil for accurate per-process CPU usage.
    """

    def __init__(self, pid: int, config: CPUThrottleConfig | None = None):
        self.pid = pid
        self.config = config or CPUThrottleConfig()
        self._stop = False
        if psutil is None:
            raise RuntimeError("psutil is required for CPU throttling. pip install psutil")
        self.proc = psutil.Process(pid)
        # Prime CPU meter
        try:
            self.proc.cpu_percent(interval=None)
        except Exception:
            pass
        self.cores = psutil.cpu_count(logical=True) or 1
        self.target_total = self.config.target_fraction * 100.0 * self.cores
        self._ema = 0.0

    def stop(self):
        self._stop = True

    def loop(self):
        while not self._stop:
            # Measure usage since last call
            usage = 0.0
            try:
                usage = self.proc.cpu_percent(interval=self.config.interval)
            except Exception:
                break
            # Smooth
            alpha = self.config.smoothing
            self._ema = alpha * usage + (1 - alpha) * self._ema
            effective = max(usage, self._ema)

            if effective > self.target_total:
                # Excess proportion above target
                over = effective - self.target_total
                p = min(0.90, max(0.05, over / effective))  # duty cycle to pause
                pause = self.config.interval * p
                # Yield time without killing the process
                try:
                    os.kill(self.pid, signal.SIGSTOP)
                    time.sleep(pause)
                    os.kill(self.pid, signal.SIGCONT)
                except ProcessLookupError:
                    break
                # Residual active time for this cycle occurs naturally while we wait next interval
            # else: run freely
