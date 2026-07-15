"""Storage layer — hybrid by design.

In production this is a **hybrid DB engine**: standard logs roll up into
ClickHouse (columnar time-series) for cheap high-volume analytics, while
structural anomalies are pushed to a vector DB for cross-cluster analysis. Offline
the default :class:`InMemoryStore` keeps template aggregates, recent anomalies and
alerts in bounded structures so the hot path never blocks on I/O; the
:class:`SqliteStore` persists the same shape, and ClickHouse/Qdrant adapters slot
in behind the same interface.

Note we aggregate per *template* rather than storing every raw line — that's what
keeps memory flat under a firehose.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections import deque
from dataclasses import dataclass, field

from .models import Alert, ParsedLog


@dataclass
class TemplateAgg:
    template_id: str
    template: str
    count: int = 0
    max_severity: int = 0
    dominant_component: str = ""
    anomaly_count: int = 0
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {"template_id": self.template_id, "template": self.template, "count": self.count,
                "max_severity": self.max_severity, "component": self.dominant_component,
                "anomaly_count": self.anomaly_count, "last_seen": self.last_seen}


class InMemoryStore:
    def __init__(self, max_anomalies: int = 5000) -> None:
        self.templates: dict[str, TemplateAgg] = {}
        self.anomalies: deque = deque(maxlen=max_anomalies)
        self.alerts: deque = deque(maxlen=2000)

    def record(self, p: ParsedLog) -> None:
        agg = self.templates.get(p.template_id)
        if agg is None:
            agg = TemplateAgg(template_id=p.template_id, template=p.template,
                              dominant_component=p.component)
            self.templates[p.template_id] = agg
        agg.count += 1
        agg.template = p.template
        agg.max_severity = max(agg.max_severity, p.severity)
        agg.dominant_component = p.component
        agg.last_seen = p.raw.ts
        if p.is_anomaly:
            agg.anomaly_count += 1
            self.anomalies.append(p.to_dict())

    def save_alert(self, alert: Alert) -> None:
        self.alerts.append(alert.to_dict())

    def top_templates(self, limit: int = 20, order: str = "count") -> list[dict]:
        key = (lambda a: a.anomaly_count) if order == "anomaly" else (lambda a: a.count)
        return [a.to_dict() for a in sorted(self.templates.values(), key=key, reverse=True)[:limit]]

    def recent_anomalies(self, limit: int = 50) -> list[dict]:
        return list(self.anomalies)[-limit:][::-1]

    def recent_alerts(self, limit: int = 50) -> list[dict]:
        return list(self.alerts)[-limit:][::-1]

    def stats(self) -> dict:
        return {"templates": len(self.templates),
                "anomalies_stored": len(self.anomalies),
                "alerts_stored": len(self.alerts)}

    def close(self) -> None:
        pass


_SCHEMA = """
CREATE TABLE IF NOT EXISTS templates (
    template_id TEXT PRIMARY KEY, template TEXT, count INTEGER, max_severity INTEGER,
    component TEXT, anomaly_count INTEGER, first_seen REAL, last_seen REAL);
CREATE TABLE IF NOT EXISTS anomalies (
    id TEXT PRIMARY KEY, template_id TEXT, severity INTEGER, component TEXT,
    reasons TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY, template_id TEXT, severity INTEGER, title TEXT,
    detail TEXT, channels TEXT, ts REAL);
"""


class SqliteStore(InMemoryStore):
    """Durable variant: keeps the in-memory hot path and flushes to SQLite."""

    def __init__(self, path: str = "logshield.db", **kw) -> None:
        super().__init__(**kw)
        self.path = path
        self._conn = sqlite3.connect(path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def flush(self) -> None:
        c = self._conn
        for a in self.templates.values():
            c.execute("INSERT OR REPLACE INTO templates VALUES (?,?,?,?,?,?,?,?)",
                      (a.template_id, a.template, a.count, a.max_severity, a.dominant_component,
                       a.anomaly_count, a.first_seen, a.last_seen))
        for an in list(self.anomalies):
            c.execute("INSERT OR REPLACE INTO anomalies VALUES (?,?,?,?,?,?)",
                      (an["id"], an["template_id"], an["severity"], an["component"],
                       json.dumps(an["anomaly_reasons"]), an["ts"]))
        for al in list(self.alerts):
            c.execute("INSERT OR REPLACE INTO alerts VALUES (?,?,?,?,?,?,?)",
                      (al["id"], al["template_id"], al["severity"], al["title"],
                       al["detail"], json.dumps(al["channels"]), al["ts"]))
        c.commit()

    def close(self) -> None:
        try:
            self.flush()
            self._conn.close()
        except sqlite3.Error:
            pass


def build_store(backend: str = "memory", path: str = "logshield.db"):
    if backend == "sqlite":
        return SqliteStore(path)
    return InMemoryStore()
