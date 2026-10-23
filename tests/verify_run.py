"""Compare a five-policy short_cl1_cu2 paper-base run with pre-migration results."""
import argparse
import json
from pathlib import Path

from common.paths import ROOT


def stable(row):
    # Wall-clock profiling, call counts, timestamps and source-directory metadata vary.
    return {k: v for k, v in row.items()
            if not k.startswith("_runner_") and not any(term in k.lower() for term in ("computation", "profiling", "timestamp"))}


def verify(folder):
    original = json.loads((ROOT / "tests/fixtures/policy_baseline.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (Path(folder) / "results.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 5, f"Expected five EV scenarios, got {len(rows)}"
    names = {"partial_labeling": "Partial Recharge/labeling/None", "full_labeling": "Full Recharge/labeling/None", "greedy": "Partial Recharge/greedy/None"}
    for row in rows:
        key = names.get(row["_runner_algorithm"], "Partial Recharge/driver/" + str(row.get("policy")))
        expected, actual = stable(original[key]), stable(row)
        different = [k for k in expected.keys() | actual.keys() if expected.get(k) != actual.get(k)]
        assert not different, f"Changed fields for {key}: {different}"
        print("MATCH", key)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    verify(parser.parse_args().run_dir)
