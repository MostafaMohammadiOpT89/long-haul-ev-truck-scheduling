"""Read canonical runs or inherited bundles without making copies for analysis."""
import json
from pathlib import Path


def read_records(path, algorithm=None):
    path = Path(path)
    if path.suffix == ".jsonl":
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload["results"] if isinstance(payload, dict) else payload
    if algorithm:
        rows = [row for row in rows if row.get("_runner_algorithm", algorithm) == algorithm]
    return rows


def read_frame(path):
    import pandas as pd
    path = Path(path)
    if path.suffix in (".jsonl", ".json"):
        return pd.DataFrame(read_records(path))
    return pd.read_csv(path, low_memory=False)
