"""Run provenance without inferring the origin of inherited results."""
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from common.paths import ROOT


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def code_state():
    def git(*args):
        result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None

    sources = {}
    for folder in ("common", "policies", "experiments", "analysis"):
        for path in sorted((ROOT / folder).rglob("*.py")):
            sources[path.relative_to(ROOT).as_posix()] = file_hash(path)
    return {"revision": git("rev-parse", "HEAD"), "working_tree_dirty": bool(git("status", "--porcelain")),
            "source_sha256": sources}


def create_manifest(preset_name, config, scenarios):
    records = [asdict(s) if is_dataclass(s) else dict(s) for s in scenarios]
    inputs = {}
    for record in records:
        instance = Path(record["instance_path"])
        if not instance.is_absolute():
            instance = ROOT / instance
        for path in sorted(instance.parent.glob("*")):
            if path.is_file():
                key = path.relative_to(ROOT).as_posix()
                if key not in inputs:
                    inputs[key] = file_hash(path)
    return {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "running", "preset": preset_name, "config": config,
            "dataset": "benchmark_v1", "input_sha256": inputs, "code": code_state(),
            "scenario_count": len(records), "completed_scenarios": 0,
            "scenarios": json.loads(json.dumps(records, default=str))}


def save_manifest(folder, manifest):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    temporary = folder / "manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary.replace(folder / "manifest.json")


def validate_run_id(run_id):
    import re
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", run_id):
        raise ValueError("Run ID must begin with a letter or digit and contain only letters, digits, _, - or .")
    return run_id
