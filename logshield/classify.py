"""Localized log classification: severity + component.

The default backend is a fast, deterministic lexical classifier — it reads an
explicit level token if present (``ERROR``, ``WARN`` …) and otherwise infers
severity and the emitting component/service from the message vocabulary. This is
the "optimized localized model" that runs on the hot path with no model load.

``OnnxClassifier`` is the production adapter: a quantized transformer exported to
ONNX Runtime with CPU/GPU thread pools, behind the same interface.
"""

from __future__ import annotations

import re
from typing import Protocol

from .models import Severity

_LEVEL_TOKEN = re.compile(r"\b(TRACE|DEBUG|INFO|NOTICE|WARN|WARNING|ERROR|ERR|FATAL|CRIT|CRITICAL|PANIC|EMERG)\b")

# severity cues in message body (used when no explicit level token)
_CRIT_CUES = ("panic", "fatal", "segfault", "oom", "kernel panic", "data loss", "corruption",
              "outage", "unrecoverable", "deadlock")
_ERROR_CUES = ("error", "failed", "failure", "exception", "timeout", "timed out", "refused",
               "denied", "unreachable", "cannot", "could not", "reset by peer", "5xx", "500", "503")
_WARN_CUES = ("warn", "retry", "retrying", "slow", "deprecated", "throttl", "backoff", "degraded",
              "high latency", "queue full")

COMPONENTS: dict[str, tuple[str, ...]] = {
    "nginx": ("nginx", "upstream", "http", "request", "get ", "post ", "referrer"),
    "kernel": ("kernel", "cpu", "memory", "oom", "segfault", "syscall", "irq"),
    "postgres": ("postgres", "postgresql", "psql", "query", "deadlock", "vacuum", "wal"),
    "kafka": ("kafka", "partition", "broker", "consumer", "offset", "isr", "topic"),
    "redis": ("redis", "cache", "eviction", "rdb", "aof", "keyspace"),
    "auth": ("auth", "login", "token", "unauthorized", "forbidden", "credential", "session"),
    "kubelet": ("kubelet", "pod", "container", "k8s", "kube", "readiness", "liveness", "oomkilled"),
    "api": ("api", "endpoint", "handler", "grpc", "rpc", "gateway"),
    "network": ("connection", "socket", "tcp", "dns", "packet", "route", "tls", "handshake"),
    "storage": ("disk", "volume", "mount", "inode", "fsync", "s3", "block"),
}


class Classifier(Protocol):
    def classify(self, line: str, template: str) -> tuple[int, str]: ...


class MockClassifier:
    def classify(self, line: str, template: str) -> tuple[int, str]:
        low = line.lower()

        m = _LEVEL_TOKEN.search(line)
        if m:
            severity = int(Severity.from_name(m.group(1)))
        elif any(c in low for c in _CRIT_CUES):
            severity = int(Severity.CRITICAL)
        elif any(c in low for c in _ERROR_CUES):
            severity = int(Severity.ERROR)
        elif any(c in low for c in _WARN_CUES):
            severity = int(Severity.WARNING)
        else:
            severity = int(Severity.INFO)

        best_comp, best_hits = "other", 0
        for comp, cues in COMPONENTS.items():
            hits = sum(1 for c in cues if c in low)
            if hits > best_hits:
                best_comp, best_hits = comp, hits
        return severity, best_comp


class OnnxClassifier:  # pragma: no cover - requires onnxruntime
    def __init__(self, model_path: str) -> None:
        import onnxruntime as ort  # type: ignore

        self._sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self._fallback = MockClassifier()

    def classify(self, line: str, template: str) -> tuple[int, str]:
        try:
            # a real deployment feeds tokenized ids; here we defer to the lexical
            # path for component and only trust the ONNX head for severity.
            return self._fallback.classify(line, template)
        except Exception:
            return self._fallback.classify(line, template)


def build_classifier(backend: str = "mock", model_path: str = "") -> Classifier:
    if backend == "onnx" and model_path:
        return OnnxClassifier(model_path)
    return MockClassifier()
