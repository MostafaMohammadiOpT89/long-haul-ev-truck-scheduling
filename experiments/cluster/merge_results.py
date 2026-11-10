"""Export completed cluster results and reconcile completion against prepared jobs."""
import argparse
import json
from common.paths import OUTPUT
from experiments.export import export_results
from experiments.provenance import validate_run_id, save_manifest

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runid", required=True)
    args = parser.parse_args()
    folder = OUTPUT / "executions" / validate_run_id(args.runid)
    rows = [json.loads(line) for line in (folder / "results.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    expected = {s["job_id"] for s in manifest["scenarios"]}
    completed = [r.get("_cluster_job_id") for r in rows]
    missing = sorted(expected - set(completed))
    duplicates = len(completed) - len(set(completed))
    manifest.update(status="completed" if not missing and not duplicates else "incomplete", completed_scenarios=len(set(completed)), missing_job_ids=missing, duplicate_results=duplicates)
    save_manifest(folder, manifest)
    print(export_results(folder))
    return 0 if manifest["status"] == "completed" else 1

if __name__ == "__main__":
    raise SystemExit(main())
