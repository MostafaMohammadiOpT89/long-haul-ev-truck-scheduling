"""Reconcile reviewer CSV exports with the existing consolidated observations.

Run: python -m experiments.audit_reviewer_results
No result files are rewritten and no repeated execution is double-counted.
"""
import ast
import csv
import hashlib
import json
import math
from collections import defaultdict

from experiments.consolidate import ROOT, configuration, decode, digest, metrics

FILES = {
    "02_base_scenario_raw/driver_heuristic_results_20261016_213428.csv": "driver_headline",
    "02_base_scenario_raw/driver_heuristic_results_tsync_sweep_20261016_213428.csv": "driver_sync",
    "02_base_scenario_raw/unified_results_full_partial_diesel_20260408_135323.csv": "base",
    "04_sensitivity_raw/cs_spacing_s1_full.csv": "spacing",
    "04_sensitivity_raw/diesel_lb_results_20260210_140456.csv": "sweep_diesel",
    "04_sensitivity_raw/unified_results_full_partial_grid_20260407_174118.csv": "sweep",
}


def equivalent(a, b):
    if a is None or b is None:
        return a is b
    if isinstance(a, (int, float)) and not isinstance(a, bool) and \
            isinstance(b, (int, float)) and not isinstance(b, bool):
        return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(equivalent(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(equivalent(a[k], b[k]) for k in a)
    return a == b


def different_fields(csv_row, original):
    differences = []
    for key, raw in csv_row.items():
        previous = original.get(key)
        if raw == "":
            same = previous is None or previous == ""
        elif key == "_cluster_job_id":
            # The CSV export drops zero padding; the archived JSON retains it.
            same = raw.isdigit() and str(previous).isdigit() and int(raw) == int(previous)
        elif isinstance(previous, (list, dict, bool, int, float)):
            try:
                same = equivalent(ast.literal_eval(raw), previous)
            except (ValueError, SyntaxError):
                same = False
        else:
            same = raw == previous
        if not same:
            differences.append(key)
    return differences


def main():
    summary_path = ROOT / "output/runs/summary_all.csv"
    if not summary_path.exists():
        summary_path = ROOT / "output/runs/summary.csv"
    before_hash = hashlib.sha256(summary_path.read_bytes()).hexdigest()
    with summary_path.open(encoding="utf-8", newline="") as stream:
        summary = {r["model_run_id"]: r for r in csv.DictReader(stream)}
    details = {}
    with (ROOT / "output/runs/details.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            details[digest(row["configuration"])] = row
    paper_ids = set((ROOT / "instances/PAPER_INSTANCE_SET_43.txt").read_text().splitlines())
    report = {
        "summary_path": str(summary_path.relative_to(ROOT)),
        "summary_sha256": before_hash,
        "comparison": "Every CSV field checked against the corresponding original "
                      "source observation, including nested schedules. Blank fields "
                      "match null/absent fields; cluster job IDs ignore zero padding; "
                      "numbers use 1e-12 relative/absolute tolerance for CSV conversion.",
        "files": [],
    }
    represented = set()
    for relative, source_id in FILES.items():
        path = ROOT / "reviewer_results" / relative
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        counts = defaultdict(int)
        counts["rows"] = len(rows)
        parameters = defaultdict(set)
        for csv_index, csv_row in enumerate(rows):
            assert csv_row["instance_id"] in paper_ids
            config = configuration(csv_row, {"id": source_id})
            for field in ("battery_kwh", "charging_power_kw", "station_spacing_km",
                          "consumption_kwh_per_km"):
                parameters[field].add(config[field])
            existing = details.get(digest(config))
            if existing is None:
                raise ValueError(f"New configuration in {relative}, row {csv_index}")
            candidates = [o for o in existing["observations"] if o["source_id"] == source_id]
            matches = [o for o in candidates if not different_fields(csv_row, decode(o["result"]))]
            if not matches:
                raise ValueError(f"Unmatched observation in {relative}, row {csv_index}")
            counts["observations_already_preserved"] += 1
            model_id = existing["model_run_id"]
            assert summary[model_id]["record_status"] == "record_available"
            represented.add(model_id)
            chosen = next(o for o in existing["observations"]
                          if o["observation_id"] == existing["selected_observation_id"])
            selected_metrics = metrics(decode(chosen["result"]))
            csv_metrics = metrics(decode(matches[0]["result"]))
            differences = [k for k in csv_metrics if not equivalent(csv_metrics[k], selected_metrics[k])]
            for field in differences:
                counts["selected_summary_differs_in_" + field] += 1
            assert set(differences) <= {"computation_seconds"}, differences
            summary_time = summary[model_id]["makespan_hours"]
            assert equivalent(float(summary_time) if summary_time else None,
                              csv_metrics["makespan_hours"])
        report["files"].append({
            "path": str(path.relative_to(ROOT)), "existing_source_id": source_id,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), **counts,
            "parameter_values": {k: sorted(v) for k, v in parameters.items()},
        })
    report["total_reviewer_rows"] = sum(f["rows"] for f in report["files"])
    report["unique_configurations_already_in_summary"] = len(represented)
    report["new_observations_to_import"] = 0
    report["summary_unchanged"] = before_hash == hashlib.sha256(summary_path.read_bytes()).hexdigest()
    assert report["summary_unchanged"]
    target = ROOT / "output/runs/reviewer_import_audit.json"
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
