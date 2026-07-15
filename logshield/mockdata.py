"""Realistic synthetic log generator.

Produces a stream that looks like real infrastructure telemetry — nginx access
lines, kernel/OOM messages, Postgres, Kafka, Redis, auth and kubelet logs — with
tunable severity mix, embedded variables (IPs, timestamps, ids, durations), and
deliberately injected **anomalies**: a burst of a rare new error template
("new incident type") plus scattered critical events. Deterministic given a seed,
so throughput numbers and anomaly recall are reproducible.
"""

from __future__ import annotations

import random
from typing import Iterator

from .models import RawLog

# (source, severity_word, template with {placeholders})
_NORMAL = [
    ("nginx", "INFO", '{ip} - - [{ts}] "GET /api/v1/users/{n} HTTP/1.1" 200 {sz}'),
    ("nginx", "INFO", '{ip} - - [{ts}] "POST /api/v1/orders HTTP/1.1" 201 {sz}'),
    ("nginx", "WARN", '{ip} - - [{ts}] "GET /api/v1/items/{n} HTTP/1.1" 404 {sz}'),
    ("postgres", "INFO", "{ts} LOG: duration: {ms}ms statement: SELECT * FROM orders WHERE id={n}"),
    ("postgres", "WARN", "{ts} WARNING: checkpoint occurring too frequently ({n} seconds apart)"),
    ("kafka", "INFO", "{ts} INFO [Consumer group-{n}] partition {n} offset committed at {n}"),
    ("redis", "INFO", "{ts} * Background saving terminated with success, {n} keys"),
    ("kubelet", "INFO", "{ts} kubelet: pod default/app-{n} readiness probe succeeded"),
    ("auth", "INFO", "{ts} INFO session {uuid} authenticated for user_{n}"),
    ("api", "INFO", "{ts} INFO request {uuid} handled in {ms}ms status=200"),
    ("network", "INFO", "{ts} connection from {ip}:{port} established on eth0"),
]
_ERRORS = [
    ("postgres", "ERROR", "{ts} ERROR: deadlock detected on relation orders pid {n}"),
    ("network", "ERROR", "{ts} ERROR connection to {ip}:{port} timed out after {ms}ms"),
    ("nginx", "ERROR", '{ip} - - [{ts}] "GET /api/v1/checkout HTTP/1.1" 503 {sz} upstream timed out'),
    ("auth", "ERROR", "{ts} ERROR unauthorized access attempt from {ip} token={uuid}"),
    ("kafka", "ERROR", "{ts} ERROR [Broker {n}] partition {n} under-replicated ISR shrank"),
    ("kubelet", "WARN", "{ts} kubelet: pod default/app-{n} liveness probe failed with err={hex}"),
]
_CRITICAL = [
    ("kernel", "CRITICAL", "{ts} kernel: Out of memory: Killed process {n} (java) total-vm:{n}kB"),
    ("kernel", "CRITICAL", "{ts} kernel: BUG: unable to handle kernel NULL pointer at {hex}"),
    ("postgres", "CRITICAL", "{ts} FATAL: could not write to file base/{n}: No space left on device"),
]
# a brand-new error pattern to inject as a spiking "new incident type"
_INCIDENT = ("payments", "ERROR",
             "{ts} ERROR payment-gateway settlement failed txn={uuid} code=GW-{n} retry exhausted")


def _fill(rng: random.Random, tpl: str) -> str:
    return (tpl
            .replace("{ip}", f"{rng.randint(10,10)}.{rng.randint(0,255)}.{rng.randint(0,255)}.{rng.randint(1,254)}")
            .replace("{ts}", "2023-08-01T12:%02d:%02d" % (rng.randint(0, 59), rng.randint(0, 59)))
            .replace("{n}", str(rng.randint(1, 99999)))
            .replace("{ms}", str(rng.randint(1, 5000)))
            .replace("{sz}", str(rng.randint(100, 99999)))
            .replace("{port}", str(rng.randint(1024, 65535)))
            .replace("{uuid}", "%08x-0000-4000-8000-%012x" % (rng.randrange(16**8), rng.randrange(16**12)))
            .replace("{hex}", "0x%X" % rng.randrange(16**6)))


def generate(n: int, seed: int = 7, error_ratio: float = 0.12, critical_ratio: float = 0.01,
             inject_incident_at: float = 0.7, incident_burst: int = 40) -> Iterator[RawLog]:
    rng = random.Random(seed)
    incident_start = int(n * inject_incident_at)
    ts = 1690891200.0
    for i in range(n):
        ts += rng.random() * 0.5
        # inject a burst of a new incident type partway through the stream
        if incident_start <= i < incident_start + incident_burst:
            src, _, tpl = _INCIDENT
        else:
            r = rng.random()
            if r < critical_ratio:
                src, _, tpl = rng.choice(_CRITICAL)
            elif r < critical_ratio + error_ratio:
                src, _, tpl = rng.choice(_ERRORS)
            else:
                src, _, tpl = rng.choice(_NORMAL)
        yield RawLog(line=_fill(rng, tpl), source=src, ts=ts)


def sample_corpus(seed: int = 1, n: int = 400) -> list[str]:
    """A small corpus for training the tokenizer."""
    return [r.line for r in generate(n, seed=seed)]
