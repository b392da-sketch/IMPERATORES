"""Run a scenario and write its record.

    python run.py scenarios/test_march.json --seed 1 --seconds 1200 --out records/test.json
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from imperatores import engine, record, scenario


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--seconds", type=float, default=1200.0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    w = scenario.load(a.scenario, a.seed)
    t0 = time.perf_counter()
    engine.run(w, a.seconds)
    elapsed = time.perf_counter() - t0
    print(f"{w.scenario_name} seed {a.seed}: {w.tick} ticks ({w.time:.0f} simulated s) "
          f"in {elapsed:.2f} s; {len(w.events)} events; digest {record.digest(w)[:16]}")
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(record.to_json(w)))
        print(f"record written to {a.out}")


if __name__ == "__main__":
    main()
