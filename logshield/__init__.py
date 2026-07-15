"""LogShield-AI — distributed, real-time AI telemetry analysis engine.

Ingests a firehose of raw infrastructure logs and, per line, parses them into
structured templates, classifies severity/component, embeds and incrementally
clusters unknown variants into "new incident types", scores anomalies, rolls up
time-series metrics, and routes critical alerts — the pipeline that sits behind
systems like Datadog / Cloudflare / Uber observability at scale.

Offline-first: every heavy dependency (ONNX transformer classifier, Kafka,
ClickHouse, Qdrant, Redis) has a fast pure-Python default, so the whole pipeline
runs, tests and benchmarks with zero external services. Real adapters wire in via
configuration for production.
"""

from .version import __version__
from .config import Settings
from .engine import LogShield

__all__ = ["__version__", "Settings", "LogShield"]
