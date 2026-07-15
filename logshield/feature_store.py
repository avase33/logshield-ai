"""Time-series aggregation feature store.

Maintains the real-time statistical metrics the dashboard and the anomaly
detector read: per-template arrival rates with an EWMA baseline (for spike
z-scores), global severity/component histograms, and a rolling logs/sec figure.

Everything is O(1) per log via exponentially-weighted moving statistics, so it
keeps up with the stream and memory stays bounded regardless of volume. The
default is in-process; a ClickHouse-backed materialisation uses the same surface.
"""

from __future__ import annotations

import math
import time
from collections import Counter, deque
from dataclasses import dataclass, field


@dataclass
class _TemplateStat:
    window_idx: int
    current_count: int = 0
    ewma_mean: float = 0.0
    ewma_var: float = 1.0
    total: int = 0
    initialized: bool = False


class TimeSeriesFeatureStore:
    def __init__(self, window_seconds: int = 60, alpha: float = 0.3) -> None:
        self.window = max(1, window_seconds)
        self.alpha = alpha
        self._templates: dict[str, _TemplateStat] = {}
        self.severity_hist: Counter = Counter()
        self.component_hist: Counter = Counter()
        self.total_logs = 0
        self.total_anomalies = 0
        self._recent_ts: deque = deque(maxlen=20000)

    def _roll(self, stat: _TemplateStat, widx: int) -> None:
        if widx == stat.window_idx:
            return
        # a window completed; fold its count into the EWMA baseline
        x = float(stat.current_count)
        if not stat.initialized:
            stat.ewma_mean = x
            stat.ewma_var = 1.0
            stat.initialized = True
        else:
            prev = stat.ewma_mean
            stat.ewma_mean = (1 - self.alpha) * prev + self.alpha * x
            stat.ewma_var = (1 - self.alpha) * (stat.ewma_var + self.alpha * (x - prev) ** 2)
        stat.window_idx = widx
        stat.current_count = 0

    def record(self, template_id: str, severity: int, component: str, ts: float | None = None,
               is_anomaly: bool = False) -> None:
        ts = ts if ts is not None else time.time()
        widx = int(ts // self.window)
        stat = self._templates.get(template_id)
        if stat is None:
            stat = _TemplateStat(window_idx=widx)
            self._templates[template_id] = stat
        self._roll(stat, widx)
        stat.current_count += 1
        stat.total += 1

        self.severity_hist[severity] += 1
        self.component_hist[component] += 1
        self.total_logs += 1
        if is_anomaly:
            self.total_anomalies += 1
        self._recent_ts.append(ts)

    def rate_z(self, template_id: str) -> float:
        stat = self._templates.get(template_id)
        if stat is None or not stat.initialized:
            return 0.0
        std = math.sqrt(max(stat.ewma_var, 1e-9))
        return (stat.current_count - stat.ewma_mean) / std

    def template_total(self, template_id: str) -> int:
        stat = self._templates.get(template_id)
        return stat.total if stat else 0

    def logs_per_second(self) -> float:
        if len(self._recent_ts) < 2:
            return 0.0
        span = self._recent_ts[-1] - self._recent_ts[0]
        return (len(self._recent_ts) / span) if span > 0 else 0.0

    def error_rate(self) -> float:
        errors = sum(c for s, c in self.severity_hist.items() if s >= 4)
        return errors / self.total_logs if self.total_logs else 0.0

    def stats(self) -> dict:
        return {
            "total_logs": self.total_logs,
            "total_anomalies": self.total_anomalies,
            "unique_templates": len(self._templates),
            "logs_per_second": round(self.logs_per_second(), 1),
            "error_rate": round(self.error_rate(), 4),
            "severity_hist": {int(k): v for k, v in sorted(self.severity_hist.items())},
            "top_components": self.component_hist.most_common(8),
        }
