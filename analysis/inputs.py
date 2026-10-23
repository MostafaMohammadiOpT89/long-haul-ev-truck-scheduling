"""Explicit saved-run selection for reproducing the inherited analyses."""
import json
import os
from pathlib import Path
from common.paths import ROOT, OUTPUT

CONFIG = Path(os.environ.get("EV_TRUCK_ANALYSIS_INPUTS", str(ROOT / "analysis/configs/paper_inputs.json")))
INPUTS = json.loads(CONFIG.read_text(encoding="utf-8"))
ANALYSIS_OUTPUT = Path(os.environ.get("EV_TRUCK_ANALYSIS_OUTPUT", str(OUTPUT / "analyses" / "paper_reproduction")))

def input_path(name):
    path = ROOT / INPUTS[name]
    if not path.is_file():
        raise FileNotFoundError(f"Missing pinned analysis input {name}: {path}")
    return path

def record_inputs(folder):
    from experiments.provenance import file_hash, code_state
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {"config": str(CONFIG), "inputs": {k: {"path": v, "sha256": file_hash(ROOT / v)} for k, v in INPUTS.items()}, "code": code_state()}
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
