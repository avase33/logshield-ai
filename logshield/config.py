"""Central configuration resolved from the environment.

Offline-first defaults keep the pipeline in-process (mock classifier, hashing
embeddings, in-memory queue + feature store + storage). Point adapters at an ONNX
model, Kafka, ClickHouse, Qdrant and Redis for production via env vars.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Settings:
    # Embeddings
    embed_dim: int = 64

    # Classifier: mock | onnx
    classifier_backend: str = "mock"
    onnx_model_path: str = ""

    # Streaming bus: memory | kafka
    bus_backend: str = "memory"
    kafka_brokers: str = "localhost:9092"
    topic: str = "logs.raw"
    partitions: int = 8

    # Storage: memory | sqlite | clickhouse
    storage_backend: str = "sqlite"
    database_url: str = "logshield.db"
    clickhouse_url: str = "http://localhost:8123"

    # Vector store: memory | qdrant
    vector_backend: str = "memory"
    qdrant_url: str = "http://localhost:6333"

    # Clustering (open-set new-incident discovery)
    cluster_similarity: float = 0.6
    min_cluster_size: int = 3

    # Anomaly detection
    rare_template_threshold: int = 3     # templates seen <= N times are "rare"
    rate_spike_z: float = 3.0            # z-score over rolling window to flag a spike

    # Alerting
    alert_min_severity: int = 4          # 0..5 (WARNING=3, ERROR=4, CRITICAL=5)
    slack_webhook: str = ""
    pagerduty_key: str = ""

    # Aggregation window
    window_seconds: int = 60

    @classmethod
    def from_env(cls) -> "Settings":
        g = os.environ.get
        return cls(
            embed_dim=int(g("LOGSHIELD_EMBED_DIM", "64")),
            classifier_backend=g("LOGSHIELD_CLASSIFIER", "mock"),
            onnx_model_path=g("LOGSHIELD_ONNX_MODEL", ""),
            bus_backend=g("LOGSHIELD_BUS", "memory"),
            kafka_brokers=g("KAFKA_BROKERS", "localhost:9092"),
            topic=g("LOGSHIELD_TOPIC", "logs.raw"),
            partitions=int(g("LOGSHIELD_PARTITIONS", "8")),
            storage_backend=g("LOGSHIELD_STORAGE", "sqlite"),
            database_url=g("LOGSHIELD_DB", "logshield.db"),
            clickhouse_url=g("CLICKHOUSE_URL", "http://localhost:8123"),
            vector_backend=g("LOGSHIELD_VECTOR", "memory"),
            qdrant_url=g("QDRANT_URL", "http://localhost:6333"),
            cluster_similarity=float(g("LOGSHIELD_CLUSTER_SIM", "0.6")),
            min_cluster_size=int(g("LOGSHIELD_MIN_CLUSTER", "3")),
            rare_template_threshold=int(g("LOGSHIELD_RARE_N", "3")),
            rate_spike_z=float(g("LOGSHIELD_SPIKE_Z", "3.0")),
            alert_min_severity=int(g("LOGSHIELD_ALERT_SEV", "4")),
            slack_webhook=g("SLACK_WEBHOOK", ""),
            pagerduty_key=g("PAGERDUTY_KEY", ""),
            window_seconds=int(g("LOGSHIELD_WINDOW", "60")),
        )
