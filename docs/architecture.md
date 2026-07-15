# Architecture

LogShield-AI is a streaming pipeline that turns a firehose of raw infrastructure
logs into structured, monitored, alertable telemetry — the shape of system that
sits behind Datadog / Cloudflare / Uber-scale observability.

## Ingestion pipeline

```
   log producers (hosts, services, k8s)
                 │
        ┌────────▼────────┐
        │ Rust receiver   │  stateless, highly concurrent (Actix-web)
        │ (src/ingestion) │  writes straight to Kafka, partitioned by source
        └────────┬────────┘
                 ▼
        ┌─────────────────┐
        │ Kafka (logs.raw)│  N partitions = max worker parallelism
        └────────┬────────┘
                 │ consume (one worker per partition)
                 ▼
   ┌───────────────────────────────────────────────────────────┐
   │ inference worker (per-line pipeline)                       │
   │                                                            │
   │  mask variables ─► Drain template ─► classify(sev,comp) ─► │
   │  embed ─► time-series aggregate ─► anomaly score ─►        │
   │  cluster unknown variants ─► persist ─► route alerts       │
   └───────────────┬───────────────────────────┬───────────────┘
                   │ standard logs             │ anomalies
                   ▼                           ▼
          ClickHouse (columnar)        Qdrant (vector DB)
          time-series analytics        cross-cluster analysis
                   │
                   ▼
        Prometheus / Grafana + /health dashboard
```

Workers scale horizontally; a Kubernetes HPA driven by **Kafka consumer lag**
(`deployment/hpa.yaml`) adds pods when the group falls behind and removes them
when it catches up.

## The AI/ML layers

### 1. Quantized tokenization
General LLM tokenizers are too slow for millions of logs/sec. LogShield trains a
compact **WordPiece/BPE-style tokenizer** (`tokenizer.py`) directly on your log
syntax, so tokenizing a line is a handful of dict lookups. It feeds a signed
hashing embedder — embedding a line is a few hashes, not a model forward pass.

### 2. Structural regex extraction + Drain templating
`parsing/masking.py` replaces volatile parameters (IPs, timestamps, UUIDs, hex
ids, durations, paths, numbers) with typed placeholders and extracts the values,
turning chaotic lines into uniform templates. `parsing/drain.py` then groups
messages with a fixed-depth **Drain** parse tree — O(depth) matching instead of
O(#templates) — giving stable templates and a stable `template_id` per group at
50k+ logs/sec.

### 3. Unsupervised open-set clustering
When a brand-new error appears, `clustering.py` groups semantically-similar
unknown/notable logs into emerging density clusters and promotes one to a **"new
incident type"** once it reaches a min-size threshold — no manual labels, no
retraining. Recently-formed clusters surface on the dashboard immediately.

### 4. Unsupervised anomaly detection
`anomaly.py` fuses cheap complementary signals — **new template**, **rare error**,
**rate spike** (EWMA z-score from the time-series feature store), and **critical
severity** — into a per-line verdict with explainable reasons.

## Scale & stability

- **Per-template aggregation**: the feature store and storage aggregate by
  template with EWMA statistics and bounded buffers, so **memory stays flat** as
  volume grows (the benchmark records RSS delta to show this).
- **Partitioned bus**: ordering per source, parallelism across partitions; the
  in-memory `PartitionedBus` models Kafka exactly for offline runs.
- **Inference acceleration**: production classifiers export to ONNX Runtime with
  CPU/GPU thread pools; offline uses the fast lexical classifier.
- **Hybrid storage**: ClickHouse for high-volume time-series, Qdrant for anomaly
  embeddings — both behind the same `storage.py` interface as the in-memory
  default.

## Offline-first

Every heavy dependency (ONNX, Kafka, ClickHouse, Qdrant, Redis) has a pure-Python
default, so the whole pipeline **runs, tests and benchmarks with zero external
services** and swaps to production adapters via environment variables.
