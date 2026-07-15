#!/usr/bin/env python3
"""Generate a synthetic log stream and (optionally) run it through the engine.

    python scripts/generate_mock_logs.py                  # 50,000 logs, show health + throughput
    python scripts/generate_mock_logs.py -n 200000        # bigger stream
    python scripts/generate_mock_logs.py --out logs.txt   # just write raw lines to a file
"""

from __future__ import annotations

import argparse
import sys
import time


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="Generate mock infrastructure logs for LogShield-AI")
    ap.add_argument("-n", "--count", type=int, default=50000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=None, help="write raw log lines to this file instead of processing")
    args = ap.parse_args(argv)

    from logshield.mockdata import generate

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            for raw in generate(args.count, seed=args.seed):
                f.write(raw.line + "\n")
        print(f"Wrote {args.count:,} log lines to {args.out}")
        return 0

    from logshield.config import Settings
    from logshield.engine import LogShield

    engine = LogShield(Settings())
    logs = list(generate(args.count, seed=args.seed))
    t0 = time.perf_counter()
    for raw in logs:
        engine.process(raw)
    elapsed = time.perf_counter() - t0
    h = engine.health()

    print(f"Processed {args.count:,} logs in {elapsed:.2f}s "
          f"({args.count/elapsed:,.0f} logs/sec, single process)")
    print(f"  templates mined   : {h['unique_templates']}")
    print(f"  error rate        : {h['error_rate']:.1%}")
    print(f"  anomalies flagged : {engine.stats.anomalies}")
    print(f"  new incident types: {h['new_incident_types']}")
    for c in engine.new_incidents()[:5]:
        print(f"    - {c['label']}: {c['sample_template'][:70]}")
    engine.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
