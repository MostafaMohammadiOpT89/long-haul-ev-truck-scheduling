import os
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


"""
Base‑scenario comparison script for TDSPEVRP
-------------------------------------------

Reads the latest base‑scenario result files for:
  - Partial Recharge main algorithm
  - Full Recharge main algorithm
  - Partial Recharge greedy scheduler

and writes comparison tables and figures under:
  Results_basescenario/

Run from the project root:
  python analyze_base_scenario.py
"""


ROOT_DIR = Path(__file__).resolve().parent


def _latest_csv(pattern: str, base_dir: Path) -> Path | None:
    """Return the most recently modified CSV matching pattern under base_dir."""
    candidates = list(base_dir.rglob(pattern))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def load_partial_results() -> pd.DataFrame:
    """Load latest Partial Recharge enhanced_main base‑scenario results."""
    base = ROOT_DIR / "Partial Recharge" / "EVTDSPalgorithmmain"
    csv_path = _latest_csv("Results/enhanced_results_*.csv", base)
    if csv_path is None:
        raise FileNotFoundError("No Partial‑Recharge enhanced_results_*.csv found")
    df = pd.read_csv(csv_path)
    # Keep essential columns and rename for clarity
    df = df[
        [
            "instance_id",
            "total_route_time_hours",
            "feasible",
            "number_of_cs_stops",
            "number_of_breaks",
            "number_of_rests",
        ]
    ].rename(
        columns={
            "total_route_time_hours": "time_partial_h",
            "feasible": "feasible_partial",
            "number_of_cs_stops": "cs_stops_partial",
            "number_of_breaks": "breaks_partial",
            "number_of_rests": "rests_partial",
        }
    )
    return df


def load_full_results() -> pd.DataFrame:
    """Load latest Full Recharge enhanced_main base‑scenario results."""
    base = ROOT_DIR / "Full Recharge" / "EVTDSPalgorithmmain"
    csv_path = _latest_csv("Results/enhanced_results_*.csv", base)
    if csv_path is None:
        raise FileNotFoundError("No Full‑Recharge enhanced_results_*.csv found")
    df = pd.read_csv(csv_path)
    df = df[
        [
            "instance_id",
            "total_route_time_hours",
            "feasible",
            "number_of_cs_stops",
            "number_of_breaks",
            "number_of_rests",
        ]
    ].rename(
        columns={
            "total_route_time_hours": "time_full_h",
            "feasible": "feasible_full",
            "number_of_cs_stops": "cs_stops_full",
            "number_of_breaks": "breaks_full",
            "number_of_rests": "rests_full",
        }
    )
    return df


def load_greedy_results() -> pd.DataFrame:
    """Load latest Partial Recharge greedy scheduler base‑scenario results."""
    base = ROOT_DIR / "Partial Recharge" / "EVTDSPalgorithmmain"
    # Prefer the recommended‑fraction file if it exists
    csv_path = _latest_csv(
        "Results/Greedy_Scheduler_Results/greedy_results_recommended_*.csv", base
    )
    if csv_path is None:
        csv_path = _latest_csv(
            "Results/Greedy_Scheduler_Results/greedy_results_*.csv", base
        )
    if csv_path is None:
        raise FileNotFoundError("No greedy_results*.csv found for greedy scheduler")

    df = pd.read_csv(csv_path)
    df = df[
        [
            "instance_id",
            "total_time",
            "feasible",
            "num_charges",
            "num_breaks",
            "num_rests",
            "safety_buffer_frac",
        ]
    ].rename(
        columns={
            "total_time": "time_greedy_h",
            "feasible": "feasible_greedy",
            "num_charges": "cs_stops_greedy",
            "num_breaks": "breaks_greedy",
            "num_rests": "rests_greedy",
        }
    )
    return df


def main() -> None:
    out_dir = ROOT_DIR / "Results_basescenario"
    out_dir.mkdir(exist_ok=True)

    # Load all three result sets
    df_partial = load_partial_results()
    df_full = load_full_results()
    df_greedy = load_greedy_results()

    # Merge on instance_id (inner join: instances present in all three)
    merged = (
        df_partial.merge(df_full, on="instance_id", how="inner")
        .merge(df_greedy, on="instance_id", how="inner")
        .sort_values("instance_id")
    )

    # Compute simple deltas
    merged["delta_partial_minus_full_h"] = merged["time_partial_h"] - merged["time_full_h"]
    merged["delta_greedy_minus_full_h"] = merged["time_greedy_h"] - merged["time_full_h"]
    merged["delta_greedy_minus_partial_h"] = (
        merged["time_greedy_h"] - merged["time_partial_h"]
    )

    # Save combined table
    merged.to_csv(out_dir / "base_scenario_combined_results.csv", index=False)

    # High‑level summary table
    summary = pd.DataFrame(
        {
            "mean_time_h": {
                "Full": merged["time_full_h"].mean(),
                "Partial": merged["time_partial_h"].mean(),
                "Greedy": merged["time_greedy_h"].mean(),
            },
            "median_time_h": {
                "Full": merged["time_full_h"].median(),
                "Partial": merged["time_partial_h"].median(),
                "Greedy": merged["time_greedy_h"].median(),
            },
        }
    )
    summary.to_csv(out_dir / "base_scenario_time_summary.csv")

    # Figure 1: per‑instance total time comparison (bar chart)
    plt.figure(figsize=(10, 6))
    x = range(len(merged))
    width = 0.25
    plt.bar(
        [i - width for i in x],
        merged["time_full_h"],
        width=width,
        label="Full Recharge",
    )
    plt.bar(
        x,
        merged["time_partial_h"],
        width=width,
        label="Partial Recharge",
    )
    plt.bar(
        [i + width for i in x],
        merged["time_greedy_h"],
        width=width,
        label="Greedy",
    )
    plt.xticks(x, merged["instance_id"], rotation=90, fontsize=7)
    plt.ylabel("Total route time (hours)")
    plt.title("Base‑scenario total route time per instance")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "base_scenario_total_time_per_instance.png", dpi=200)
    plt.close()

    # Figure 2: distribution of time deltas (greedy/partial vs full)
    plt.figure(figsize=(8, 5))
    plt.hist(
        merged["delta_partial_minus_full_h"],
        bins=20,
        alpha=0.7,
        label="Partial - Full",
    )
    plt.hist(
        merged["delta_greedy_minus_full_h"],
        bins=20,
        alpha=0.7,
        label="Greedy - Full",
    )
    plt.xlabel("Time difference (hours)")
    plt.ylabel("Number of instances")
    plt.title("Base‑scenario time difference vs Full Recharge")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "base_scenario_time_deltas_vs_full.png", dpi=200)
    plt.close()

    print(f"Combined base‑scenario results written to: {out_dir}")


if __name__ == "__main__":
    main()

