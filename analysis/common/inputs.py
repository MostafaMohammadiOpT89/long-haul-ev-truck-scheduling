"""Explicit saved-run selection for reproducing the inherited analyses."""
import json
import os
from pathlib import Path
from common.paths import ROOT, OUTPUT
from common.results import ResultSelection

CONFIG = Path(os.environ.get("EV_TRUCK_ANALYSIS_INPUTS", str(ROOT / "analysis/configs/paper_inputs.json")))
INPUTS = json.loads(CONFIG.read_text(encoding="utf-8"))
ANALYSIS_OUTPUT = Path(os.environ.get("EV_TRUCK_ANALYSIS_OUTPUT", str(ROOT / "analysis")))

def input_path(name):
    spec = INPUTS[name]
    path = ROOT / (spec['path'] if isinstance(spec, dict) else spec)
    if not path.is_file():
        raise FileNotFoundError(f"Missing pinned analysis input {name}: {path}")
    return path

def input_source(name):
    spec = INPUTS[name]
    path = input_path(name)
    if isinstance(spec, dict):
        return ResultSelection(path, spec['source_id'], spec.get('algorithm'))
    return path

def record_inputs(folder):
    from experiments.provenance import file_hash, code_state
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {"config": str(CONFIG), "inputs": {k: {"selection": v, "sha256": file_hash(input_path(k))} for k, v in INPUTS.items()}, "code": code_state()}
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
