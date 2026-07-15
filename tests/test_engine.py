import pytest

from logshield.config import Settings
from logshield.engine import LogShield
from logshield.mockdata import generate
from logshield.streaming.bus import PartitionedBus, partition_for
from logshield.alerting import AlertingAgent, MockSlack, MockPagerDuty
from logshield.models import Severity


@pytest.fixture(scope="module")
def engine():
    eng = LogShield(Settings())
    eng.ingest_many(generate(3000, seed=7))
    return eng


def test_engine_mines_templates_and_flags_anomalies(engine):
    h = engine.health()
    assert h["unique_templates"] > 3
    assert engine.stats.anomalies > 0
    assert 0.0 < h["error_rate"] < 1.0


def test_engine_discovers_new_incident(engine):
    # the injected payment-gateway burst should surface as a new incident type
    incidents = engine.new_incidents()
    assert len(incidents) >= 1
    assert any("payment" in c["sample_template"] or "settlement" in c["sample_template"]
               for c in incidents)


def test_engine_routes_alerts(engine):
    alerts = engine.store.recent_alerts(100)
    assert len(alerts) > 0
    assert any("pagerduty" in a["channels"] for a in alerts)  # criticals page


def test_partitioning_is_stable():
    assert partition_for("hostA", 8) == partition_for("hostA", 8)


def test_bus_and_worker_pool():
    eng = LogShield(Settings())
    bus: PartitionedBus = eng.bus
    for raw in generate(500, seed=3):
        eng.produce(raw)
    assert bus.consumer_lag() == 500
    pool = eng.worker_pool()
    processed = pool.drain()
    assert processed == 500
    assert bus.consumer_lag() == 0
    assert pool.stats.processed == 500


def test_alerting_dedup_and_routing():
    slack, pager = MockSlack(), MockPagerDuty()
    agent = AlertingAgent(min_severity=int(Severity.ERROR), cooldown_seconds=9999,
                          slack=slack, pager=pager)
    a1 = agent.route("tpl1", int(Severity.CRITICAL), "kernel", "oom killed", ["critical_severity"])
    a2 = agent.route("tpl1", int(Severity.CRITICAL), "kernel", "oom killed", ["critical_severity"])
    assert a1 is not None and a2 is None          # deduped within cooldown
    assert "pagerduty" in a1.channels and "slack" in a1.channels
    assert len(pager.sent) == 1
    # INFO with no reasons -> not routed
    assert agent.route("tpl2", int(Severity.INFO), "api", "ok", []) is None
