import math

from logshield.tokenizer import train
from logshield.embeddings import HashingEmbedder, cosine
from logshield.classify import MockClassifier
from logshield.clustering import IncrementalClusterer
from logshield.anomaly import AnomalyDetector
from logshield.feature_store import TimeSeriesFeatureStore
from logshield.models import Severity
from logshield.mockdata import sample_corpus


def test_tokenizer_trains_and_encodes():
    tok = train(sample_corpus(n=120), vocab_size=800)
    assert tok.size > 50
    ids = tok.encode_ids("connection timeout on api gateway")
    assert len(ids) > 0
    # deterministic
    assert tok.encode("connection failed") == tok.encode("connection failed")


def test_embeddings_unit_and_semantic():
    tok = train(sample_corpus(n=120), vocab_size=800)
    emb = HashingEmbedder(tok, dim=64)
    a = emb.embed("connection to server timed out")
    b = emb.embed("connection to host timed out")
    c = emb.embed("background save completed successfully")
    assert abs(math.sqrt(sum(x * x for x in a)) - 1.0) < 1e-9
    assert cosine(a, b) > cosine(a, c)


def test_classifier_severity_and_component():
    clf = MockClassifier()
    sev, comp = clf.classify("2023 ERROR deadlock detected on relation orders", "")
    assert sev == int(Severity.ERROR)
    assert comp == "postgres"
    sev2, _ = clf.classify("kernel: Out of memory: Killed process", "")
    assert sev2 == int(Severity.CRITICAL)
    sev3, _ = clf.classify("INFO request handled", "")
    assert sev3 == int(Severity.INFO)


def test_incremental_clustering_promotes():
    emb = HashingEmbedder(train(sample_corpus(n=120), vocab_size=800), dim=64)
    clu = IncrementalClusterer(similarity=0.5, min_cluster_size=3)
    for _ in range(3):
        clu.assign(emb.embed("payment gateway settlement failed retry exhausted"),
                   "payments", int(Severity.ERROR), "payment gateway settlement failed")
    assert len(clu.clusters) == 1
    assert clu.clusters[0].members == 3
    assert clu.new_incidents()


def test_anomaly_rules():
    det = AnomalyDetector(rare_threshold=3, spike_z=3.0)
    assert det.evaluate(int(Severity.CRITICAL), False, 100, 0.0).is_anomaly
    assert "new_template" in det.evaluate(int(Severity.ERROR), True, 1, 0.0).reasons
    assert "rare_error" in det.evaluate(int(Severity.ERROR), False, 2, 0.0).reasons
    assert "rate_spike" in det.evaluate(int(Severity.INFO), False, 500, 5.0).reasons
    assert not det.evaluate(int(Severity.INFO), False, 500, 0.0).is_anomaly


def test_feature_store_rate_and_stats():
    fs = TimeSeriesFeatureStore(window_seconds=10)
    # build a baseline across several windows, then a spike in the current window
    for w in range(5):
        for _ in range(2):
            fs.record("t1", int(Severity.INFO), "api", ts=w * 10 + 1)
    for i in range(20):
        fs.record("t1", int(Severity.INFO), "api", ts=100 + i * 0.1)
    assert fs.rate_z("t1") > 2.0
    st = fs.stats()
    assert st["total_logs"] > 0 and st["unique_templates"] == 1
