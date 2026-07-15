"""Unsupervised anomaly detection over the log stream.

Combines cheap, complementary signals into an anomaly verdict per log line — no
labels required:

* **new template** — a structure the system has never seen before (open-set),
  meaningful when it carries at least a warning;
* **rare error** — a template seen only a handful of times that is an ERROR/CRIT;
* **rate spike** — the per-template arrival rate jumps above ``z`` standard
  deviations of its recent history (a burst), from the time-series feature store;
* **critical** — anything at CRITICAL severity is always surfaced.

Each firing reason is recorded so the dashboard can explain *why* a line was
flagged.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Severity


@dataclass
class AnomalyVerdict:
    is_anomaly: bool
    reasons: list[str]


class AnomalyDetector:
    def __init__(self, rare_threshold: int = 3, spike_z: float = 3.0) -> None:
        self.rare_threshold = rare_threshold
        self.spike_z = spike_z

    def evaluate(self, severity: int, is_new_template: bool, template_count: int,
                 rate_z: float) -> AnomalyVerdict:
        reasons: list[str] = []

        if severity >= int(Severity.CRITICAL):
            reasons.append("critical_severity")
        if is_new_template and severity >= int(Severity.WARNING):
            reasons.append("new_template")
        if template_count <= self.rare_threshold and severity >= int(Severity.ERROR):
            reasons.append("rare_error")
        if rate_z >= self.spike_z:
            reasons.append("rate_spike")

        return AnomalyVerdict(is_anomaly=bool(reasons), reasons=reasons)
