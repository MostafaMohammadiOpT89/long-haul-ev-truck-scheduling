"""Repository paths shared by every supported entry point."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "instances" / "benchmark_v1"
OUTPUT = ROOT / "output"
