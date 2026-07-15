"""Partitioned message bus (Kafka-style).

The receiver writes each raw log to a partition chosen by a stable hash of its
source key, so all logs from one host/service land on the same partition and
preserve order, while different partitions are consumed in parallel by different
workers. The default :class:`PartitionedBus` is an in-memory model of exactly
this with identical semantics; :class:`KafkaBus` is the production adapter.
"""

from __future__ import annotations

import hashlib
import threading
from collections import deque
from typing import Optional


def partition_for(key: str, partitions: int) -> int:
    h = int.from_bytes(hashlib.md5(key.encode()).digest()[:4], "big")
    return h % partitions


class PartitionedBus:
    def __init__(self, partitions: int = 8) -> None:
        self.partitions = partitions
        self._queues: list[deque] = [deque() for _ in range(partitions)]
        self._offsets: list[int] = [0] * partitions   # consumer offsets
        self._produced: list[int] = [0] * partitions
        self._lock = threading.Lock()

    def produce(self, key: str, message: dict) -> int:
        p = partition_for(key, self.partitions)
        with self._lock:
            self._queues[p].append(message)
            self._produced[p] += 1
        return p

    def poll(self, partition: int, max_records: int = 500) -> list[dict]:
        q = self._queues[partition]
        out: list[dict] = []
        while q and len(out) < max_records:
            out.append(q.popleft())
        self._offsets[partition] += len(out)
        return out

    def consumer_lag(self) -> int:
        """Total unconsumed messages across partitions — the HPA scaling signal."""
        return sum(len(q) for q in self._queues)

    def pending(self, partition: int) -> int:
        return len(self._queues[partition])

    def total_produced(self) -> int:
        return sum(self._produced)


class KafkaBus:  # pragma: no cover - requires kafka
    def __init__(self, brokers: str, topic: str = "logs.raw", partitions: int = 8) -> None:
        from kafka import KafkaConsumer, KafkaProducer  # type: ignore
        import json

        self.topic = topic
        self.partitions = partitions
        self._producer = KafkaProducer(bootstrap_servers=brokers,
                                       value_serializer=lambda v: json.dumps(v).encode(),
                                       key_serializer=lambda k: k.encode())
        self._json = json

    def produce(self, key: str, message: dict) -> int:
        fut = self._producer.send(self.topic, key=key, value=message)
        return fut.get(timeout=10).partition

    def poll(self, partition: int, max_records: int = 500):
        raise NotImplementedError("KafkaBus is consumed by dedicated consumer processes")


def build_bus(backend: str = "memory", brokers: str = "", topic: str = "logs.raw",
              partitions: int = 8) -> PartitionedBus:
    if backend == "kafka" and brokers:
        return KafkaBus(brokers, topic, partitions)  # type: ignore[return-value]
    return PartitionedBus(partitions)
