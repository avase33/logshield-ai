"""Command-line interface for LogShield-AI."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from .benchmark import benchmark
from .config import Settings
from .engine import LogShield
from .logging_setup import configure_logging
from .mockdata import generate
from .models import Severity
from .version import __version__


def _reconfigure_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass


def cmd_demo(args) -> int:
    engine = LogShield(Settings())
    engine.ingest_many(generate(args.count, seed=args.seed))
    health = engine.health()

    print(f"LogShield-AI demo — processed {engine.stats.total:,} logs")
    print(f"  throughput sample : run `logshield bench` for logs/sec")
    print(f"  unique templates  : {health['unique_templates']}")
    print(f"  error rate        : {health['error_rate']:.1%}")
    print(f"  anomalies flagged : {engine.stats.anomalies}")
    print(f"  new incident types: {health['new_incident_types']}")
    print("\nNew incident types discovered (open-set clustering):")
    for c in engine.new_incidents()[:args.top]:
        print(f"  - {c['label']:<22} members={c['members']:<4} "
              f"sev={Severity(c['max_severity']).name:<8} :: {c['sample_template'][:70]}")
    print("\nRecent alerts routed:")
    for a in engine.store.recent_alerts(args.top):
        print(f"  -> {'+'.join(a['channels']):<16} {a['title'][:80]}")
    engine.close()
    return 0


def cmd_bench(args) -> int:
    rep = benchmark(n=args.count, seed=args.seed)
    print(json.dumps(rep.to_dict(), indent=2))
    return 0


def cmd_health(args) -> int:
    engine = LogShield(Settings())
    engine.ingest_many(generate(args.count, seed=args.seed))
    print(json.dumps(engine.health(), indent=2, default=str))
    engine.close()
    return 0


def cmd_ingest(args) -> int:
    engine = LogShield(Settings())
    src = sys.stdin if args.file == "-" else open(args.file, encoding="utf-8", errors="replace")
    n = 0
    try:
        for line in src:
            line = line.rstrip("\n")
            if line:
                engine.ingest(line, source=args.source)
                n += 1
    finally:
        if src is not sys.stdin:
            src.close()
    print(f"Ingested {n} lines. Health: {json.dumps(engine.health(), default=str)}")
    engine.close()
    return 0


def cmd_serve(args) -> int:
    from .serving.api import run_server

    run_server(host=args.host, port=args.port, count=args.count, seed=args.seed)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="logshield", description="Real-time AI telemetry analysis engine")
    p.add_argument("--version", action="version", version=f"logshield {__version__}")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--seed", type=int, default=7)
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("demo", help="ingest synthetic logs and show the health picture")
    d.add_argument("-c", "--count", type=int, default=5000)
    d.add_argument("--top", type=int, default=8)
    d.set_defaults(func=cmd_demo)

    b = sub.add_parser("bench", help="throughput + memory benchmark")
    b.add_argument("-c", "--count", type=int, default=50000)
    b.set_defaults(func=cmd_bench)

    h = sub.add_parser("health", help="print the system health JSON")
    h.add_argument("-c", "--count", type=int, default=5000)
    h.set_defaults(func=cmd_health)

    i = sub.add_parser("ingest", help="ingest log lines from a file (- for stdin)")
    i.add_argument("file")
    i.add_argument("--source", default="file")
    i.set_defaults(func=cmd_ingest)

    sv = sub.add_parser("serve", help="run the FastAPI health-dashboard server")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("-c", "--count", type=int, default=5000)
    sv.set_defaults(func=cmd_serve)
    return p


def main(argv: Optional[list[str]] = None) -> int:
    _reconfigure_stdout()
    args = build_parser().parse_args(argv)
    configure_logging("DEBUG" if args.verbose else "WARNING")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
