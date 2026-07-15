"""FastAPI serving API + real-time health dashboard.

    POST /ingest          ingest one or many raw log lines
    GET  /health          system health snapshot (logs/sec, error rate, lag, ...)
    GET  /incidents       discovered "new incident types" (open-set clusters)
    GET  /templates       top mined templates
    GET  /anomalies       recent flagged anomalies
    GET  /alerts          recently routed alerts
    GET  /metrics         Prometheus exposition
    GET  /                the live health dashboard (React via CDN, no build step)

FastAPI/uvicorn are optional; import this module only when serving. An engine is
pre-seeded with synthetic logs at startup so the dashboard is demoable instantly.
"""

from __future__ import annotations

from typing import Optional

from ..config import Settings
from ..engine import LogShield
from ..mockdata import generate


def create_app(count: int = 5000, seed: int = 7, engine: Optional[LogShield] = None):
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
    from pydantic import BaseModel

    app = FastAPI(title="LogShield-AI", version="0.1.0",
                  description="Distributed real-time AI telemetry analysis engine")

    if engine is None:
        engine = LogShield(Settings())
        if count:
            engine.ingest_many(generate(count, seed=seed))
    app.state.engine = engine

    class IngestBody(BaseModel):
        lines: list[str]
        source: str = "api"

    @app.post("/ingest")
    def ingest(body: IngestBody) -> dict:
        eng: LogShield = app.state.engine
        anomalies = 0
        for line in body.lines:
            if line.strip():
                p = eng.ingest(line, source=body.source)
                anomalies += int(p.is_anomaly)
        return {"ingested": len(body.lines), "anomalies": anomalies}

    @app.get("/health")
    def health() -> JSONResponse:
        return JSONResponse(app.state.engine.health())

    @app.get("/incidents")
    def incidents() -> JSONResponse:
        return JSONResponse(app.state.engine.new_incidents())

    @app.get("/templates")
    def templates(top: int = 20) -> JSONResponse:
        return JSONResponse(app.state.engine.store.top_templates(limit=top))

    @app.get("/anomalies")
    def anomalies(limit: int = 50) -> JSONResponse:
        return JSONResponse(app.state.engine.store.recent_anomalies(limit=limit))

    @app.get("/alerts")
    def alerts(limit: int = 50) -> JSONResponse:
        return JSONResponse(app.state.engine.store.recent_alerts(limit=limit))

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/metrics", response_class=PlainTextResponse)
    def metrics() -> str:
        h = app.state.engine.health()
        sev = h["severity_hist"]
        lines = [
            "# TYPE logshield_logs_total counter",
            f"logshield_logs_total {h['total_logs']}",
            "# TYPE logshield_logs_per_second gauge",
            f"logshield_logs_per_second {h['logs_per_second']}",
            "# TYPE logshield_error_rate gauge",
            f"logshield_error_rate {h['error_rate']}",
            "# TYPE logshield_anomalies_total counter",
            f"logshield_anomalies_total {h['anomalies']}",
            "# TYPE logshield_unique_templates gauge",
            f"logshield_unique_templates {h['unique_templates']}",
            "# TYPE logshield_new_incident_types gauge",
            f"logshield_new_incident_types {h['new_incident_types']}",
            "# TYPE logshield_kafka_consumer_lag gauge",
            f"logshield_kafka_consumer_lag {h['consumer_lag']}",
        ]
        for s, c in sev.items():
            lines.append(f'logshield_logs_by_severity{{severity="{s}"}} {c}')
        return "\n".join(lines) + "\n"

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        from .dashboard import DASHBOARD_HTML
        return DASHBOARD_HTML

    return app


def run_server(host: str = "127.0.0.1", port: int = 8000, count: int = 5000,
               seed: int = 7) -> None:  # pragma: no cover
    import uvicorn

    uvicorn.run(create_app(count=count, seed=seed), host=host, port=port)
