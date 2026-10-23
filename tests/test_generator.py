"""Check seeded generation independently of process-global randomness."""
import contextlib
import io
from pathlib import Path
import random
import tempfile
from types import SimpleNamespace
import unittest

from instances.generator.main import run_grid


class GeneratorTests(unittest.TestCase):
    def test_seed_reproduces_full_grid_despite_global_random_state(self):
        state = random.getstate()
        try:
            with tempfile.TemporaryDirectory() as directory:
                snapshots = []
                for index, global_seed in enumerate((11, 987)):
                    random.seed(global_seed)
                    target = Path(directory) / str(index)
                    args = SimpleNamespace(seed=42, out=str(target), round_trip=True,
                                           no_baatsfjord=False, add_unbalanced_variant=True)
                    with contextlib.redirect_stdout(io.StringIO()):
                        run_grid(args)
                    snapshots.append({p.relative_to(target).as_posix(): p.read_bytes()
                                      for p in target.rglob('*') if p.is_file()})
                self.assertEqual(len(snapshots[0]), 227)
                self.assertEqual(snapshots[0], snapshots[1])
        finally:
            random.setstate(state)


if __name__ == '__main__':
    unittest.main()
