import pytest

from logshield.cli import main
from logshield.mockdata import generate


def test_cli_demo(capsys):
    assert main(["demo", "--count", "1500"]) == 0
    out = capsys.readouterr().out.lower()
    assert "logs" in out and "incident" in out


def test_cli_bench(capsys):
    assert main(["bench", "--count", "2000"]) == 0
    out = capsys.readouterr().out
    assert "throughput_logs_per_sec" in out


def test_cli_version():
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0


def test_mockdata_deterministic():
    a = [r.line for r in generate(200, seed=5)]
    b = [r.line for r in generate(200, seed=5)]
    assert a == b


def test_api_endpoints():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from logshield.serving.api import create_app

    client = TestClient(create_app(count=1500, seed=7))
    assert client.get("/healthz").json()["status"] == "ok"

    h = client.get("/health").json()
    assert h["total_logs"] >= 1500

    r = client.post("/ingest", json={"lines": [
        "2023-08-01T12:00:00 ERROR brand new never seen widget exploded code=XYZ",
    ], "source": "test"})
    assert r.status_code == 200

    assert isinstance(client.get("/incidents").json(), list)
    assert isinstance(client.get("/templates?top=5").json(), list)
    metrics = client.get("/metrics").text
    assert "logshield_logs_total" in metrics
    assert "LogShield" in client.get("/").text
