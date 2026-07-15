"""Throughput + memory-stability benchmark.

Streams a large batch of synthetic logs through the full pipeline and reports
sustained throughput (logs/sec), the number of templates mined, anomalies caught
and new incident types discovered. Because the engine aggregates per-template and
uses bounded buffers, memory stays flat as volume grows — the benchmark records
the RSS delta (when ``psutil`` is available) to demonstrate that.

Absolute throughput scales with cores and with the Rust receiver + multiple Kafka
partitions in production; this single-process number is the per-worker floor.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class BenchReport:
    logs: int
    elapsed_s: float
    throughput_lps: float
    templates: int
    anomalies: int
    new_incidents: int
    rss_delta_mb: float | None

    def to_dict(self) -> dict:
        d = {"logs": self.logs, "elapsed_s": round(self.elapsed_s, 3),
             "throughput_logs_per_sec": round(self.throughput_lps, 0),
             "templates": self.templates, "anomalies": self.anomalies,
             "new_incidents": self.new_incidents}
        if self.rss_delta_mb is not None:
            d["rss_delta_mb"] = round(self.rss_delta_mb, 2)
        return d


def _rss_mb():
    try:
        import os
        import psutil  # type: ignore
        return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    except Exception:
        return None


def benchmark(n: int = 50000, seed: int = 7, settings=None) -> BenchReport:
    from .config import Settings
    from .engine import LogShield
    from .mockdata import generate

    engine = LogShield(settings or Settings())
    logs = list(generate(n, seed=seed))   # pre-generate so we time only the pipeline

    rss0 = _rss_mb()
    t0 = time.perf_counter()
    for raw in logs:
        engine.process(raw)
    elapsed = time.perf_counter() - t0
    rss1 = _rss_mb()

    fs = engine.full_stats()
    report = BenchReport(
        logs=n, elapsed_s=elapsed, throughput_lps=n / elapsed if elapsed else 0.0,
        templates=fs["features"]["unique_templates"], anomalies=engine.stats.anomalies,
        new_incidents=engine.stats.new_incidents,
        rss_delta_mb=(rss1 - rss0) if (rss0 is not None and rss1 is not None) else None,
    )
    engine.close()
    return report
