"""Inference worker pool.

Consumes raw-log messages from bus partitions and runs each through the parsing +
classification + clustering + anomaly pipeline. In production each worker is a
process pinned to a Kafka partition running the ONNX model; offline the pool
drains the in-memory partitioned bus in batches with the same per-message logic,
so throughput and correctness are testable without a broker.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..logging_setup import get_logger
from ..models import RawLog
from .bus import PartitionedBus

log = get_logger("worker")


@dataclass
class WorkerStats:
    consumed: int = 0
    processed: int = 0
    errors: int = 0

    def to_dict(self) -> dict:
        return {"consumed": self.consumed, "processed": self.processed, "errors": self.errors}


class InferenceWorkerPool:
    def __init__(self, bus: PartitionedBus, handler: Callable[[RawLog], object],
                 batch_size: int = 500) -> None:
        self.bus = bus
        self.handler = handler
        self.batch_size = batch_size
        self.stats = WorkerStats()

    def _handle_message(self, msg: dict) -> None:
        raw = RawLog(line=msg.get("line", ""), source=msg.get("source", "unknown"),
                     ts=msg.get("ts", 0.0) or __import__("time").time())
        self.stats.consumed += 1
        try:
            self.handler(raw)
            self.stats.processed += 1
        except Exception as exc:  # keep the worker alive on a bad line
            self.stats.errors += 1
            log.debug("worker error: %s", exc)

    def drain(self) -> int:
        """Process all currently-buffered messages across every partition."""
        total = 0
        for p in range(self.bus.partitions):
            while True:
                batch = self.bus.poll(p, self.batch_size)
                if not batch:
                    break
                for msg in batch:
                    self._handle_message(msg)
                total += len(batch)
        return total
