"""Create a flat CSV summary from canonical JSONL results."""
import argparse
import csv
import json
from pathlib import Path


def export_results(run_dir):
    run_dir = Path(run_dir)
    with (run_dir / "results.jsonl").open(encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    # Full timelines and decision logs remain in the canonical file.
    fields = sorted({key for row in rows for key, value in row.items()
                     if not isinstance(value, (list, dict))})
    out = run_dir / "exports" / "results.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) if not isinstance(row.get(key), (list, dict)) else ""
                             for key in fields})
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    print(export_results(args.run_dir))


if __name__ == "__main__":
    main()
