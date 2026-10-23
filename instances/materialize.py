"""Materialize a cataloged dataset into a new directory without duplicating stored inputs."""
import argparse
import csv
import hashlib
from pathlib import Path
import shutil

from common.paths import ROOT


def materialize(dataset, destination):
    destination = Path(destination).resolve()
    with (ROOT / "instances/catalog.csv").open(encoding="utf-8", newline="") as stream:
        rows = [row for row in csv.DictReader(stream) if row["dataset"] == dataset]
    if not rows:
        raise ValueError(f"Unknown dataset: {dataset}")
    if destination.exists():
        raise FileExistsError(f"Choose a new output directory: {destination}")
    # Verify all source files before creating anything.
    for row in rows:
        source = ROOT / row["path"]
        if hashlib.sha256(source.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError(f"Dataset source changed: {source}")
        if not (destination / row["logical_path"]).resolve().is_relative_to(destination):
            raise ValueError("Invalid logical dataset path")
    destination.mkdir(parents=True)
    for row in rows:
        target = destination / row["logical_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / row["path"], target)
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", choices=["benchmark_v1", "legacy_generator_variant"])
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(f"Materialized {materialize(args.dataset, args.destination)} files")
