"""Locust load test — vectorized log-stream simulator.

Drives the ingest API with batches of realistic synthetic log lines to prove the
system sustains 50,000+ logs/sec. Each task posts a batch (default 200 lines), so
a modest number of users generates a very high line rate.

    logshield serve
    locust -f load-testing/locustfile.py --host http://localhost:8000 \
           --headless -u 200 -r 50 -t 2m
"""

from __future__ import annotations

import random

try:
    from locust import HttpUser, between, task
except Exception:  # pragma: no cover - locust optional
    HttpUser = object  # type: ignore

    def task(*a, **k):
        def deco(f):
            return f
        return deco

    def between(*a, **k):
        return 0

_TEMPLATES = [
    '10.0.{a}.{b} - - [2023-08-01T12:00:00] "GET /api/v1/users/{n} HTTP/1.1" 200 {n}',
    '2023-08-01T12:00:00 LOG: duration: {n}ms statement: SELECT * FROM orders WHERE id={n}',
    '2023-08-01T12:00:00 ERROR connection to 10.0.{a}.{b}:{n} timed out after {n}ms',
    '2023-08-01T12:00:00 kernel: Out of memory: Killed process {n} (java)',
    '2023-08-01T12:00:00 INFO [Consumer group-{n}] partition {n} offset committed at {n}',
]


def _batch(rng: random.Random, size: int = 200) -> list[str]:
    out = []
    for _ in range(size):
        t = rng.choice(_TEMPLATES)
        out.append(t.replace("{a}", str(rng.randint(0, 255)))
                    .replace("{b}", str(rng.randint(1, 254)))
                    .replace("{n}", str(rng.randint(1, 99999))))
    return out


class LogProducer(HttpUser):  # pragma: no cover - executed by locust
    wait_time = between(0.0, 0.02)

    def on_start(self):
        self._rng = random.Random()

    @task
    def ingest_batch(self):
        self.client.post("/ingest", json={"source": "loadtest", "lines": _batch(self._rng, 200)},
                         name="/ingest [batch=200]")
