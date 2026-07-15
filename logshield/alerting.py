"""Graph-based alert routing agent.

Runs each flagged event through a small routing graph whose conditional edges
decide escalation and destination:

    triage --(critical)--> page + notify
           --(rate spike / rare error)--> notify
           --(new incident type)--> incident channel
           --(else)--> drop

De-duplicates by template within a cooldown window so a burst of the same error
pages once, not thousands of times. Dispatchers are pluggable — the defaults are
deterministic mocks recording what *would* be sent; real Slack/PagerDuty adapters
implement the same call interface.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .logging_setup import get_logger
from .models import Alert, Severity

log = get_logger("alerting")

Dispatcher = Callable[[Alert], str]


class MockSlack:
    def __init__(self) -> None:
        self.sent: list[Alert] = []

    def __call__(self, alert: Alert) -> str:
        self.sent.append(alert)
        log.info("[slack] %s", alert.title)
        return f"slack://{alert.id}"


class MockPagerDuty:
    def __init__(self) -> None:
        self.sent: list[Alert] = []

    def __call__(self, alert: Alert) -> str:
        self.sent.append(alert)
        log.info("[pagerduty] PAGE %s", alert.title)
        return f"pd://{alert.id}"


@dataclass
class AlertingAgent:
    min_severity: int = int(Severity.ERROR)
    cooldown_seconds: float = 300.0
    slack: Dispatcher = field(default_factory=MockSlack)
    pager: Dispatcher = field(default_factory=MockPagerDuty)
    _last_sent: dict[str, float] = field(default_factory=dict)

    def _cooling_down(self, template_id: str, now: float) -> bool:
        last = self._last_sent.get(template_id)
        return last is not None and (now - last) < self.cooldown_seconds

    def route(self, template_id: str, severity: int, component: str, template: str,
              reasons: list[str], new_incident: bool = False,
              store=None) -> Optional[Alert]:
        now = time.time()
        worth_it = (severity >= self.min_severity) or bool(reasons) or new_incident
        if not worth_it or self._cooling_down(template_id, now):
            return None

        channels: list[str] = []
        # --- routing graph edges ---
        if severity >= int(Severity.CRITICAL) or "critical_severity" in reasons:
            channels = ["pagerduty", "slack"]
        elif "rate_spike" in reasons or "rare_error" in reasons or severity >= int(Severity.ERROR):
            channels = ["slack"]
        elif new_incident or "new_template" in reasons:
            channels = ["slack"]

        if not channels:
            return None

        title = f"[{component}] {_sev_name(severity)} — {template[:80]}"
        detail = (f"template={template_id} severity={_sev_name(severity)} "
                  f"reasons={','.join(reasons) or 'threshold'}"
                  + (" NEW-INCIDENT" if new_incident else ""))
        alert = Alert(template_id=template_id, severity=severity, title=title,
                      detail=detail, channels=channels)

        if "pagerduty" in channels:
            self.pager(alert)
        if "slack" in channels:
            self.slack(alert)
        self._last_sent[template_id] = now
        if store is not None:
            store.save_alert(alert)
        return alert


def _sev_name(sev: int) -> str:
    try:
        return Severity(sev).name
    except ValueError:
        return str(sev)
