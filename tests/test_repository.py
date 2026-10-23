"""Integrity and orchestration checks for the reorganized repository."""
import csv
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from dataclasses import asdict

from common.paths import ROOT, BENCHMARK
from experiments import run
from experiments.cluster.create_jobs import _build_jobs
from instances.materialize import materialize


class RepositoryTests(unittest.TestCase):
    def test_catalog_checksums_and_complete_datasets(self):
        with (ROOT / "instances/catalog.csv").open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        for dataset in ("benchmark_v1", "legacy_generator_variant"):
            subset = [r for r in rows if r["dataset"] == dataset]
            self.assertEqual(len(subset), 227)
            self.assertEqual(len({r["instance_id"] for r in subset if r["instance_id"]}), 45)
            for row in subset:
                self.assertEqual(hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest(), row["sha256"], row["path"])

    def test_alternate_dataset_can_be_reconstructed(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "dataset"
            self.assertEqual(materialize("legacy_generator_variant", destination), 227)
            name = "short_cl1_cu2"
            self.assertNotEqual((destination / name / (name + "_DistanceMatrix.csv")).read_bytes(),
                                (BENCHMARK / name / (name + "_DistanceMatrix.csv")).read_bytes())

    def test_solver_imports_are_isolated(self):
        full = importlib.import_module("policies.labeling.full_recharge.single_scenario_runner")
        partial = importlib.import_module("policies.labeling.partial_recharge.single_scenario_runner")
        self.assertIsNot(full.network, partial.network)
        self.assertIsNot(full.label, partial.label)

    def test_local_and_cluster_enumeration_agree(self):
        name, path = run._discover_instances(BENCHMARK)[0]
        for preset_name in ("paper_base", "parameter_sweep", "driver_sync_sweep"):
            preset = run.PRESETS[preset_name]
            local = run._build_scenarios([(name, path)], [(name, path)], preset)
            cluster = _build_jobs(preset, [(name, path, path)], True, frozenset(run.ALL_ALGORITHMS))
            def normalize(record):
                data = asdict(record)
                data.pop("job_id", None)
                data["tag"] = data.get("tag") or ""
                for key in ("consumption", "distance_per_cs", "battery_cap", "charging_power", "safety_buffer_frac", "t_sync_hours"):
                    if data.get(key) is not None:
                        data[key] = float(data[key])
                data["instance_path"] = str((ROOT / data["instance_path"]).resolve())
                return json.dumps(data, sort_keys=True)
            self.assertEqual(sorted(map(normalize, local)), sorted(map(normalize, cluster)), preset_name)

    def test_analysis_inputs_exist(self):
        config = json.loads((ROOT / "analysis/configs/paper_inputs.json").read_text())
        for path in config.values():
            self.assertTrue((ROOT / path).is_file(), path)

    def test_preserved_noncode_assets(self):
        manifest = json.loads((ROOT / "docs/migration_manifest.json").read_text())
        for record in manifest["files"]:
            if Path(record["original"]).suffix in (".py", ".md", ".sh") or record["original"] in (".gitignore", "requirements.txt"):
                continue
            self.assertEqual(hashlib.sha256((ROOT / record["destination"]).read_bytes()).hexdigest(), record["sha256"], record["original"])


if __name__ == "__main__":
    unittest.main()
