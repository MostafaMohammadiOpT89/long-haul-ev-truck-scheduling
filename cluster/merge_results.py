#!/usr/bin/env python3
"""
Merge cluster raw outputs into unified-style bundles (combined + per-algorithm JSON/CSV).

Input:
  Results/Cluster/output_<runid>.jsonl

Output:
  Results/Cluster/merged/<runid>/
    unified_results_<runid>.json/.csv
    partial_labeling_results_<runid>.json/.csv
    full_labeling_results_<runid>.json/.csv
    greedy_results_<runid>.json/.csv
    diesel_lb_results_<runid>.json/.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List


ROOT_DIR = Path(__file__).resolve().parents[1]


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({k for r in rows for k in r.keys()})
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _save_bundle(out_dir: Path, stem: str, meta: Dict[str, Any], rows: List[Dict[str, Any]]) -> None:
    payload = {"metadata": meta, "results": rows}
    _write_json(out_dir / f"{stem}.json", payload)
    _write_csv(out_dir / f"{stem}.csv", rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runid", required=True)
    args = parser.parse_args()

    runid = args.runid
    raw_jsonl = ROOT_DIR / "Results" / "Cluster" / f"output_{runid}.jsonl"
    if not raw_jsonl.exists():
        print(f"ERROR: missing {raw_jsonl}")
        return 1

    rows = _read_jsonl(raw_jsonl)
    if not rows:
        print("ERROR: no rows found in jsonl")
        return 1

    out_dir = ROOT_DIR / "Results" / "Cluster" / "merged" / runid

    meta_base = {
        "runid": runid,
        "raw_input": str(raw_jsonl.relative_to(ROOT_DIR)),
        "total_rows": len(rows),
    }

    # Combined
    _save_bundle(out_dir, f"unified_results_{runid}", meta_base, rows)

    # Per algorithm
    by_algo: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        algo = str(r.get("_runner_algorithm", "unknown"))
        by_algo.setdefault(algo, []).append(r)

    for algo, a_rows in by_algo.items():
        _save_bundle(out_dir, f"{algo}_results_{runid}", {**meta_base, "algorithm": algo, "total_rows": len(a_rows)}, a_rows)

    # Diesel only
    diesel_rows = [r for r in rows if str(r.get("_runner_tag", "")) == "diesel_lb"]
    if diesel_rows:
        _save_bundle(out_dir, f"diesel_lb_results_{runid}", {**meta_base, "tag": "diesel_lb", "total_rows": len(diesel_rows)}, diesel_rows)

    print(f"Merged outputs written to: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

