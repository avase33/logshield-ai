"""Core domain models (dataclasses)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


def new_id(prefix: str = "id") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Severity(IntEnum):
    TRACE = 0
    DEBUG = 1
    INFO = 2
    WARNING = 3
    ERROR = 4
    CRITICAL = 5

    @classmethod
    def from_name(cls, name: str) -> "Severity":
        return _SEV_ALIASES.get(name.strip().lower(), cls.INFO)


_SEV_ALIASES = {
    "trace": Severity.TRACE, "trc": Severity.TRACE,
    "debug": Severity.DEBUG, "dbg": Severity.DEBUG,
    "info": Severity.INFO, "information": Severity.INFO, "notice": Severity.INFO,
    "warn": Severity.WARNING, "warning": Severity.WARNING,
    "error": Severity.ERROR, "err": Severity.ERROR, "fail": Severity.ERROR, "failed": Severity.ERROR,
    "critical": Severity.CRITICAL, "crit": Severity.CRITICAL, "fatal": Severity.CRITICAL,
    "emergency": Severity.CRITICAL, "panic": Severity.CRITICAL,
}


@dataclass
class RawLog:
    line: str
    source: str = "unknown"
    ts: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: new_id("log"))


@dataclass
class ParsedLog:
    raw: RawLog
    template: str                    # masked template, e.g. "connection to <IP> failed <NUM>"
    template_id: str                 # stable hash of the template
    severity: int                    # Severity value
    component: str                   # inferred component/service
    variables: dict[str, list[str]] = field(default_factory=dict)  # extracted params by type
    embedding: list[float] = field(default_factory=list)
    cluster_id: str | None = None
    is_anomaly: bool = False
    anomaly_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.raw.id, "ts": self.raw.ts, "source": self.raw.source,
                "template": self.template, "template_id": self.template_id,
                "severity": self.severity, "component": self.component,
                "cluster_id": self.cluster_id, "is_anomaly": self.is_anomaly,
                "anomaly_reasons": self.anomaly_reasons}


@dataclass
class Cluster:
    id: str
    label: str
    centroid: list[float]
    members: int = 0
    dominant_component: str = ""
    max_severity: int = 0
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    new_incident: bool = True
    sample_template: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "members": self.members,
                "dominant_component": self.dominant_component, "max_severity": self.max_severity,
                "new_incident": self.new_incident, "sample_template": self.sample_template}


@dataclass
class Alert:
    template_id: str
    severity: int
    title: str
    detail: str
    channels: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: new_id("alert"))
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "template_id": self.template_id, "severity": self.severity,
                "title": self.title, "detail": self.detail, "channels": self.channels, "ts": self.ts}
