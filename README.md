<div align="center">

# LogShield-AI

### Distributed, real-time AI telemetry analysis engine

Ingests a firehose of raw infrastructure logs and, per line, parses them into
structured templates, classifies severity/component, detects anomalies, and
clusters brand-new errors into **"new incident types"** — updating a live system
health dashboard. Built for **50,000+ logs/sec** with unsupervised open-set
anomaly detection.

[![CI](https://github.com/avase33/logshield-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/avase33/logshield-ai/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%20|%203.11%20|%203.12-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/lint-ruff-000000.svg)](https://github.com/astral-sh/ruff)

</div>

---

## The scale challenge

Infrastructure at scale emits terabytes of logs per hour. The hard part is
consuming, parsing, embedding and analyzing that non-stop flood **without lag or
dropped data** — and surfacing the handful of lines that actually matter. LogShield
is a streaming pipeline that does exactly that:

```
Rust receiver → Kafka → inference workers
   (mask → Drain template → classify → embed → aggregate → anomaly → cluster → alert)
→ ClickHouse + Qdrant → Prometheus/Grafana + live health dashboard
```

## What's implemented (and actually runs)

Every stage is **built from scratch in pure Python** and the whole thing runs,
tests and benchmarks with **zero external services**:

- **Quantized tokenizer** — a WordPiece/BPE tokenizer trained on log syntax, so
  tokenizing is dict lookups, not a slow general tokenizer.
- **Structural masking + Drain templating** — turns chaotic lines into uniform
  templates (`<IP>`, `<TIMESTAMP>`, `<NUM>`, …) with O(depth) template matching
  and extracted variables.
- **Localized classifier** — severity + component per line (ONNX adapter for
  production).
- **Open-set incremental clustering** — groups never-seen errors into emerging
  **new incident types**, no labels, no retraining.
- **Unsupervised anomaly detection** — new-template / rare-error / rate-spike
  (EWMA z-score) / critical, with explainable reasons.
- **Time-series feature store** — per-template rates + severity/component
  histograms in O(1) with bounded memory.
- **Partitioned streaming bus + worker pool** — Kafka-style partitioning and
  parallel consumption.
- **Graph-based alert routing** — Slack / PagerDuty with per-template dedup.
- **FastAPI + live health dashboard** (`/ingest`, `/health`, `/incidents`,
  `/metrics`).

Production adapters (ONNX Runtime, Kafka, ClickHouse, Qdrant, Redis) switch on via
environment variables and never change the pipeline logic.

## Quickstart (no dependencies)

```bash
pip install -e .

# Ingest a synthetic stream and show the health picture + discovered incidents
logshield demo

# Throughput + memory benchmark
logshield bench --count 50000

# Generate a 200k-line stream and process it
python scripts/generate_mock_logs.py -n 200000
```

Example (`logshield demo`):

```
LogShield-AI demo — processed 5,000 logs
  unique templates  : 22
  error rate        : 13.8%
  anomalies flagged : 148
  new incident types: 10

New incident types discovered (open-set clustering):
  - Payments incident   members=40  sev=ERROR  :: <TIMESTAMP> ERROR payment-gateway settlement failed ...
  - Kernel incident      members=8   sev=CRIT   :: <TIMESTAMP> kernel: Out of memory: Killed process ...
  ...
```

> A tiny offline self-check trains + runs the whole pipeline on 2,000 logs in
> **~0.7s** (`python verify_tiny.py`). Absolute throughput scales with cores and
> with the Rust receiver + Kafka partitions; the single-process number is the
> per-worker floor.

## Serve the dashboard

```bash
pip install -e ".[serve]"
logshield serve            # http://localhost:8000  (live health dashboard)
```

```
POST /ingest {lines:[...]}   ingest raw log lines
GET  /health                 logs/sec, error rate, lag, incidents
GET  /incidents              discovered new incident types
GET  /templates | /anomalies | /alerts
GET  /metrics                Prometheus exposition
```

## Scale validation

```bash
logshield bench --count 50000
# {"throughput_logs_per_sec": ..., "templates": ..., "anomalies": ...,
#  "new_incidents": ..., "rss_delta_mb": ...}   # memory stays flat
```

Load testing to 50k+ logs/sec against a live server:

```bash
locust -f load-testing/locustfile.py --host http://localhost:8000 --headless -u 200 -r 50 -t 2m
# or
k6 run -e HOST=http://localhost:8000 load-testing/k6-script.js
```

## Full infrastructure

```bash
# Kafka + ClickHouse + Redis + Qdrant + Prometheus + Grafana + the worker
docker compose -f docker-compose.infra.yml up --build

# Kubernetes with HPA driven by Kafka consumer lag
kubectl apply -f deployment/deployment.yaml -f deployment/hpa.yaml
helm install logshield deployment/helm
```

## Repository layout

```
logshield/
  tokenizer.py       WordPiece/BPE tokenizer trained on log syntax
  parsing/           masking (structural regex) + Drain templating
  classify.py        severity + component classifier (ONNX adapter)
  clustering.py      open-set incremental clustering (new incident types)
  anomaly.py         unsupervised anomaly detection
  feature_store.py   time-series aggregation (EWMA rates)
  streaming/         partitioned bus + inference worker pool
  alerting.py        graph-based alert routing (Slack/PagerDuty)
  storage.py         in-memory / SQLite / ClickHouse+Qdrant
  engine.py          pipeline wiring   |   serving/ (FastAPI + dashboard)
src/ingestion/       Rust (Actix-web) high-throughput receiver
src/streaming-bus/   Kafka topic/partition config
deployment/          k8s Deployment, HPA (Kafka lag), Helm, Prometheus/Grafana
load-testing/        Locust + k6 log-stream simulators
docker-compose.infra.yml, Dockerfile, .github/workflows/ci.yml
```

## Development

```bash
pip install -e ".[serve,dev]"
pytest --cov=logshield
ruff check logshield scripts
python verify_logshield.py       # full offline end-to-end self-check
```

## License

MIT © Akhil Vase
