"""Read canonical runs or inherited bundles without making copies for analysis."""
import json
from pathlib import Path
from dataclasses import dataclass


@dataclass(frozen=True)
class ResultSelection:
    """An explicit source cohort inside the consolidated details file."""
    path: Path
    source_id: str
    algorithm: str | None = None

    def __fspath__(self):
        return str(self.path)

    def __str__(self):
        return f'{self.path} [source={self.source_id}, algorithm={self.algorithm or "all"}]'

    @property
    def parent(self):
        return self.path.parent

    @property
    def name(self):
        return self.path.name

    @property
    def stem(self):
        return self.path.stem

    def exists(self):
        return self.path.exists()

    def is_file(self):
        return self.path.is_file()


def read_records(path, algorithm=None):
    if isinstance(path, ResultSelection):
        from experiments.consolidate import source_records
        rows = source_records(path.source_id, path.path)
        for policy in (path.algorithm, algorithm):
            if policy:
                rows = [r for r in rows if r.get('_runner_algorithm') == policy]
        return rows
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
    if isinstance(path, ResultSelection):
        return pd.DataFrame(read_records(path))
    path = Path(path)
    if path.suffix in (".jsonl", ".json"):
        return pd.DataFrame(read_records(path))
    return pd.read_csv(path, low_memory=False)
