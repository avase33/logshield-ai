"""LogShield — the engine that wires the telemetry pipeline together.

Per log line:

    mask variables -> Drain template -> classify (severity+component) -> embed ->
    time-series aggregate -> anomaly score -> cluster unknown variants -> persist
    -> route alerts

One object is shared by the CLI, API, worker pool, tests and benchmarks. It is
synchronous and pure so it runs and is measurable with no external services.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from .alerting import AlertingAgent
from .anomaly import AnomalyDetector
from .classify import build_classifier
from .clustering import IncrementalClusterer
from .config import Settings
from .embeddings import HashingEmbedder
from .feature_store import TimeSeriesFeatureStore
from .logging_setup import get_logger
from .mockdata import sample_corpus
from .models import ParsedLog, RawLog, Severity
from .parsing.drain import DrainParser
from .parsing.masking import extract_variables, mask
from .storage import build_store
from .streaming.bus import build_bus
from .streaming.worker import InferenceWorkerPool
from .tokenizer import Tokenizer, train

log = get_logger("engine")


@dataclass
class IngestStats:
    total: int = 0
    anomalies: int = 0
    alerts: int = 0
    new_incidents: int = 0


class LogShield:
    def __init__(self, settings: Optional[Settings] = None, tokenizer: Optional[Tokenizer] = None) -> None:
        self.settings = settings or Settings()
        s = self.settings
        # a tokenizer trained on masked templates from a seed corpus (so placeholders
        # like <ip>/<num> are in-vocab); retrain on real traffic via train_tokenizer
        self.tokenizer = tokenizer or train((mask(l) for l in sample_corpus(n=300)), vocab_size=1500)
        self.embedder = HashingEmbedder(self.tokenizer, dim=s.embed_dim)
        self.drain = DrainParser()
        self.classifier = build_classifier(s.classifier_backend, s.onnx_model_path)
        self.clusterer = IncrementalClusterer(s.cluster_similarity, s.min_cluster_size)
        self.features = TimeSeriesFeatureStore(s.window_seconds)
        self.detector = AnomalyDetector(s.rare_template_threshold, s.rate_spike_z)
        self.alerting = AlertingAgent(min_severity=s.alert_min_severity)
        self.store = build_store(s.storage_backend if s.storage_backend != "clickhouse" else "memory",
                                 s.database_url)
        self.bus = build_bus(s.bus_backend, s.kafka_brokers, s.topic, s.partitions)
        self.stats = IngestStats()

    def train_tokenizer(self, corpus: Iterable[str], vocab_size: int = 2000) -> None:
        self.tokenizer = train(corpus, vocab_size=vocab_size)
        self.embedder = HashingEmbedder(self.tokenizer, dim=self.settings.embed_dim)

    # ---- core pipeline --------------------------------------------------

    def process(self, raw: RawLog) -> ParsedLog:
        template = mask(raw.line)
        pr = self.drain.add(template)
        severity, component = self.classifier.classify(raw.line, pr.template)

        # anomaly signals computed against state *before* recording this log
        rate_z = self.features.rate_z(pr.template_id)
        verdict = self.detector.evaluate(severity, pr.is_new, pr.matched_count, rate_z)
        self.features.record(pr.template_id, severity, component, raw.ts, verdict.is_anomaly)

        parsed = ParsedLog(raw=raw, template=pr.template, template_id=pr.template_id,
                           severity=severity, component=component,
                           is_anomaly=verdict.is_anomaly, anomaly_reasons=verdict.reasons)

        new_incident = False
        # embed + cluster the interesting minority: anomalies, never-seen templates,
        # and anything at ERROR+ severity (keeps the hot path cheap for normal INFO logs)
        if verdict.is_anomaly or pr.is_new or severity >= int(Severity.ERROR):
            parsed.embedding = self.embedder.embed(pr.template)
            res = self.clusterer.assign(parsed.embedding, component, severity, pr.template)
            parsed.cluster_id = res.cluster_id
            lv = self.clusterer._live.get(res.cluster_id)  # noqa: SLF001
            new_incident = bool(lv and not lv.provisional and lv.cluster.new_incident)

        self.store.record(parsed)
        self.stats.total += 1
        if verdict.is_anomaly:
            self.stats.anomalies += 1

        alert = self.alerting.route(pr.template_id, severity, component, pr.template,
                                    verdict.reasons, new_incident=new_incident, store=self.store)
        if alert is not None:
            self.stats.alerts += 1
        if new_incident:
            self.stats.new_incidents += 1
        return parsed

    # ---- ingestion ------------------------------------------------------

    def ingest(self, line: str, source: str = "unknown") -> ParsedLog:
        return self.process(RawLog(line=line, source=source))

    def ingest_many(self, raws: Iterable[RawLog]) -> IngestStats:
        for raw in raws:
            self.process(raw)
        return self.stats

    def worker_pool(self, batch_size: int = 500) -> InferenceWorkerPool:
        return InferenceWorkerPool(self.bus, self.process, batch_size=batch_size)

    def produce(self, raw: RawLog) -> int:
        return self.bus.produce(raw.source, {"line": raw.line, "source": raw.source, "ts": raw.ts})

    # ---- read models ----------------------------------------------------

    def new_incidents(self) -> list[dict]:
        return [c.to_dict() for c in self.clusterer.new_incidents()]

    def health(self) -> dict:
        fs = self.features.stats()
        return {
            "logs_per_second": fs["logs_per_second"],
            "error_rate": fs["error_rate"],
            "total_logs": fs["total_logs"],
            "anomalies": self.stats.anomalies,
            "unique_templates": fs["unique_templates"],
            "new_incident_types": len(self.clusterer.new_incidents()),
            "consumer_lag": self.bus.consumer_lag(),
            "severity_hist": fs["severity_hist"],
            "top_components": fs["top_components"],
        }

    def full_stats(self) -> dict:
        return {"ingest": vars(self.stats), "features": self.features.stats(),
                "store": self.store.stats(), "clusters": len(self.clusterer.clusters)}

    def close(self) -> None:
        self.store.close()
