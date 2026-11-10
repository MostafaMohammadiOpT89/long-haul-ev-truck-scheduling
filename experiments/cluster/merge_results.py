"""Export completed cluster results and reconcile completion against prepared jobs.

results.jsonl keeps every attempt (also failed ones and retries). This script keeps one
final row per job (the last "ok" row, otherwise the last attempt), writes it to
results_final.jsonl and exports/results.csv, and records missing and failed jobs in the manifest.
Rows without job_status come from older runs and count as ok.
"""
import argparse
import json
from common.paths import OUTPUT
from experiments.export import export_results
from experiments.provenance import validate_run_id, save_manifest


def _job_id(row):
    return row.get("_cluster_job_id") or row.get("job_job_id")


def final_rows(rows):
    best = {}
    for row in rows:
        key = _job_id(row)
        ok = row.get("job_status", "ok") == "ok"
        if key not in best or ok or best[key].get("job_status", "ok") != "ok":
            best[key] = row
    return best


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runid", required=True)
    args = parser.parse_args()
    folder = OUTPUT / "executions" / validate_run_id(args.runid)
    rows = []
    source = folder / "results.jsonl"
    if not source.exists():
        print(f"No results yet in {source}")
        return 1
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # half-written line from a killed node
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    expected = {s["job_id"] for s in manifest["scenarios"]}
    best = final_rows(rows)
    ok_ids = {k for k, r in best.items() if r.get("job_status", "ok") == "ok"}
    failed = sorted(k for k, r in best.items() if r.get("job_status", "ok") != "ok")
    missing = sorted(expected - set(best))
    with (folder / "results_final.jsonl").open("w", encoding="utf-8") as out:
        for key in sorted(best, key=str):
            out.write(json.dumps(best[key]) + "\n")
    manifest.update(status="completed" if not missing and not failed else "incomplete",
                    completed_scenarios=len(ok_ids & expected), missing_job_ids=missing,
                    failed_job_ids=failed, attempts_in_results_jsonl=len(rows))
    save_manifest(folder, manifest)
    print(f"ok: {len(ok_ids & expected)} / {len(expected)}  failed: {len(failed)}  never ran: {len(missing)}")
    print(export_results(folder, source="results_final.jsonl"))
    return 0 if manifest["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
