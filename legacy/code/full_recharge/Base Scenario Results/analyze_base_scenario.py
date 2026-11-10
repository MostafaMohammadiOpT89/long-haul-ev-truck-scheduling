from pathlib import Path
import re

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

"""
Comprehensive Base-Scenario Comparison Analysis for TDSPEVRP
============================================================

Operations Research Framework:
1. Algorithm-level KPIs: Time, Charging, HoS, Synchronization
2. Grouped Analysis: Route class (short/med/long), Allocation (Balanced/Unbalanced)
3. Comparative Metrics: Percentage improvements, efficiency ratios
4. Synchronization Impact: Time savings, event synchronization rates

Outputs:
- Detailed comparison tables (CSV)
- Comprehensive figures (PNG)
- Summary statistics by dimension
"""

ROOT_DIR = Path(__file__).resolve().parent


def _latest_csv(pattern: str) -> Path | None:
    """Return the most recently modified CSV in ROOT_DIR matching pattern."""
    candidates = list(ROOT_DIR.glob(pattern))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def extract_instance_features(instance_id: str) -> dict:
    """Extract route class, clusters, customers, and allocation from instance_id."""
    # Pattern: {route_class}_cl{clusters}_cu{customers}_{allocation}
    # Examples: long_cl3_cu12_Balanced, short_cl1_cu2, med_cl2_cu4_Unbalanced
    
    parts = instance_id.split('_')
    route_class = parts[0]  # short, med, long
    
    clusters = None
    customers = None
    allocation = "N/A"  # Default for single-cluster instances
    
    for part in parts[1:]:
        if part.startswith('cl'):
            clusters = int(part[2:])
        elif part.startswith('cu'):
            customers = int(part[2:])
        elif part in ['Balanced', 'Unbalanced']:
            allocation = part
    
    return {
        'route_class': route_class,
        'clusters': clusters,
        'customers': customers,
        'allocation': allocation
    }


def load_partial_results() -> pd.DataFrame:
    """Load Partial Recharge enhanced_main base-scenario results."""
    csv_path = _latest_csv("partial_recharge_enhanced_results_*.csv")
    if csv_path is None:
        raise FileNotFoundError("No partial_recharge_enhanced_results_*.csv found")
    
    df = pd.read_csv(csv_path)
    
    # Extract all relevant columns
    df = df[[
        "instance_id",
        "total_route_time_hours",
        "feasible",
        "number_of_cs_stops",
        "number_of_breaks",
        "number_of_rests",
        "number_of_synchronized_events",
        "number_of_unsynchronized_charging_events",
        "number_of_unsynchronized_breaks",
        "number_of_unsynchronized_rests",
        "total_idle_charging_time_minutes",
        "percentage_of_charging_events_synchronized",
        "computation_time_seconds",
        "number_of_labels_generated",
    ]].rename(columns={
        "total_route_time_hours": "time_partial_h",
        "feasible": "feasible_partial",
        "number_of_cs_stops": "cs_stops_partial",
        "number_of_breaks": "breaks_partial",
        "number_of_rests": "rests_partial",
        "number_of_synchronized_events": "sync_events_partial",
        "number_of_unsynchronized_charging_events": "unsync_charges_partial",
        "number_of_unsynchronized_breaks": "unsync_breaks_partial",
        "number_of_unsynchronized_rests": "unsync_rests_partial",
        "total_idle_charging_time_minutes": "idle_charge_time_partial_min",
        "percentage_of_charging_events_synchronized": "sync_pct_partial",
        "computation_time_seconds": "comp_time_partial_s",
        "number_of_labels_generated": "labels_partial",
    })
    
    # Add instance features
    features = pd.DataFrame([extract_instance_features(inst) for inst in df['instance_id']])
    df = pd.concat([df, features], axis=1)
    
    return df


def load_full_results() -> pd.DataFrame:
    """Load Full Recharge enhanced_main base-scenario results."""
    csv_path = _latest_csv("full_recharge_enhanced_results_*.csv")
    if csv_path is None:
        raise FileNotFoundError("No full_recharge_enhanced_results_*.csv found")
    
    df = pd.read_csv(csv_path)
    
    df = df[[
        "instance_id",
        "total_route_time_hours",
        "feasible",
        "number_of_cs_stops",
        "number_of_breaks",
        "number_of_rests",
        "number_of_synchronized_events",
        "number_of_unsynchronized_charging_events",
        "number_of_unsynchronized_breaks",
        "number_of_unsynchronized_rests",
        "total_idle_charging_time_minutes",
        "percentage_of_charging_events_synchronized",
        "computation_time_seconds",
        "number_of_labels_generated",
    ]].rename(columns={
        "total_route_time_hours": "time_full_h",
        "feasible": "feasible_full",
        "number_of_cs_stops": "cs_stops_full",
        "number_of_breaks": "breaks_full",
        "number_of_rests": "rests_full",
        "number_of_synchronized_events": "sync_events_full",
        "number_of_unsynchronized_charging_events": "unsync_charges_full",
        "number_of_unsynchronized_breaks": "unsync_breaks_full",
        "number_of_unsynchronized_rests": "unsync_rests_full",
        "total_idle_charging_time_minutes": "idle_charge_time_full_min",
        "percentage_of_charging_events_synchronized": "sync_pct_full",
        "computation_time_seconds": "comp_time_full_s",
        "number_of_labels_generated": "labels_full",
    })
    
    return df


def load_greedy_results() -> pd.DataFrame:
    """Load Partial Recharge greedy scheduler base-scenario results."""
    csv_path = _latest_csv("greedy_results_recommended_*.csv")
    if csv_path is None:
        csv_path = _latest_csv("greedy_results_*.csv")
    if csv_path is None:
        raise FileNotFoundError("No greedy_results*.csv found")
    
    df = pd.read_csv(csv_path)
    
    # Check if new columns exist (updated greedy scheduler with full metrics)
    available_cols = df.columns.tolist()
    base_cols = ["instance_id", "total_time", "feasible", "num_charges", "num_breaks", "num_rests", 
                 "num_synchronized_events", "safety_buffer_frac"]
    
    # Try to get new columns if available (from updated greedy scheduler)
    new_cols = ["num_unsynchronized_charging_events", "num_unsynchronized_breaks", 
                "num_unsynchronized_rests", "total_idle_charging_time_minutes",
                "percentage_of_charging_events_synchronized"]
    
    cols_to_select = base_cols + [col for col in new_cols if col in available_cols]
    df = df[cols_to_select]
    
    df = df.rename(columns={
        "total_time": "time_greedy_h",
        "feasible": "feasible_greedy",
        "num_charges": "cs_stops_greedy",
        "num_breaks": "breaks_greedy",
        "num_rests": "rests_greedy",
        "num_synchronized_events": "sync_events_greedy",
    })
    
    # Map new columns if they exist, otherwise set defaults (for backward compatibility)
    if "num_unsynchronized_charging_events" in df.columns:
        df = df.rename(columns={"num_unsynchronized_charging_events": "unsync_charges_greedy"})
    else:
        df["unsync_charges_greedy"] = 0
    
    if "num_unsynchronized_breaks" in df.columns:
        df = df.rename(columns={"num_unsynchronized_breaks": "unsync_breaks_greedy"})
    else:
        df["unsync_breaks_greedy"] = 0
    
    if "num_unsynchronized_rests" in df.columns:
        df = df.rename(columns={"num_unsynchronized_rests": "unsync_rests_greedy"})
    else:
        df["unsync_rests_greedy"] = 0
    
    if "total_idle_charging_time_minutes" in df.columns:
        df = df.rename(columns={"total_idle_charging_time_minutes": "idle_charge_time_greedy_min"})
    else:
        df["idle_charge_time_greedy_min"] = 0.0
    
    if "percentage_of_charging_events_synchronized" in df.columns:
        df = df.rename(columns={"percentage_of_charging_events_synchronized": "sync_pct_greedy"})
    else:
        # Fallback: calculate from sync_events if available
        df["sync_pct_greedy"] = df.apply(
            lambda row: 100.0 if row.get("sync_events_greedy", 0) > 0 and row.get("cs_stops_greedy", 0) > 0 
            else 0.0, axis=1
        )
    
    df["comp_time_greedy_s"] = 0.0  # Greedy is very fast
    df["labels_greedy"] = 0  # Greedy doesn't use labeling
    
    return df


def compute_comparative_metrics(merged: pd.DataFrame) -> pd.DataFrame:
    """Compute all comparative KPIs and metrics."""
    df = merged.copy()
    
    # ===== TIME METRICS =====
    # Absolute time differences
    df["delta_partial_minus_full_h"] = df["time_partial_h"] - df["time_full_h"]
    df["delta_greedy_minus_full_h"] = df["time_greedy_h"] - df["time_full_h"]
    df["delta_greedy_minus_partial_h"] = df["time_greedy_h"] - df["time_partial_h"]
    
    # Percentage time improvements (negative = improvement, positive = worse)
    df["pct_improvement_partial_vs_full"] = (
        (df["time_full_h"] - df["time_partial_h"]) / df["time_full_h"] * 100
    )
    df["pct_improvement_greedy_vs_full"] = (
        (df["time_full_h"] - df["time_greedy_h"]) / df["time_full_h"] * 100
    )
    df["pct_improvement_greedy_vs_partial"] = (
        (df["time_partial_h"] - df["time_greedy_h"]) / df["time_partial_h"] * 100
    )
    
    # Time per customer (efficiency metric)
    df["time_per_customer_full"] = df["time_full_h"] / df["customers"]
    df["time_per_customer_partial"] = df["time_partial_h"] / df["customers"]
    df["time_per_customer_greedy"] = df["time_greedy_h"] / df["customers"]
    
    # ===== CHARGING METRICS =====
    # Charging frequency (stops per 100km - approximate, using route class)
    route_class_dist = {"short": 1000, "med": 2000, "long": 3500}  # Approximate distances
    df["approx_distance_km"] = df["route_class"].map(route_class_dist)
    df["charge_freq_full"] = df["cs_stops_full"] / df["approx_distance_km"] * 100
    df["charge_freq_partial"] = df["cs_stops_partial"] / df["approx_distance_km"] * 100
    df["charge_freq_greedy"] = df["cs_stops_greedy"] / df["approx_distance_km"] * 100
    
    # Charging stop differences
    df["delta_cs_partial_minus_full"] = df["cs_stops_partial"] - df["cs_stops_full"]
    df["delta_cs_greedy_minus_full"] = df["cs_stops_greedy"] - df["cs_stops_full"]
    df["delta_cs_greedy_minus_partial"] = df["cs_stops_greedy"] - df["cs_stops_partial"]
    
    # ===== HOS METRICS =====
    # Total HoS stops (breaks + rests)
    df["total_hos_stops_full"] = df["breaks_full"] + df["rests_full"]
    df["total_hos_stops_partial"] = df["breaks_partial"] + df["rests_partial"]
    df["total_hos_stops_greedy"] = df["breaks_greedy"] + df["rests_greedy"]
    
    # HoS stop differences
    df["delta_hos_partial_minus_full"] = df["total_hos_stops_partial"] - df["total_hos_stops_full"]
    df["delta_hos_greedy_minus_full"] = df["total_hos_stops_greedy"] - df["total_hos_stops_full"]
    
    # ===== SYNCHRONIZATION METRICS =====
    # Synchronization event counts
    df["delta_sync_partial_minus_full"] = df["sync_events_partial"] - df["sync_events_full"]
    df["delta_sync_greedy_minus_full"] = df["sync_events_greedy"] - df["sync_events_full"]
    
    # Synchronization percentage (already in data)
    # Idle time savings (time saved by synchronization)
    df["idle_time_savings_partial_h"] = df["idle_charge_time_partial_min"] / 60.0
    df["idle_time_savings_full_h"] = df["idle_charge_time_full_min"] / 60.0
    df["idle_time_savings_greedy_h"] = df["idle_charge_time_greedy_min"] / 60.0
    
    # ===== ALGORITHM EFFICIENCY =====
    # Computation time (for exact algorithms)
    df["comp_time_ratio_partial_vs_full"] = df["comp_time_partial_s"] / df["comp_time_full_s"]
    
    return df


def create_summary_tables(merged: pd.DataFrame, out_dir: Path):
    """Create comprehensive summary tables by different dimensions."""
    
    # ===== TABLE 1: Overall Summary Statistics =====
    summary_overall = pd.DataFrame({
        "Metric": [
            "Mean Time (h)", "Median Time (h)", "Std Time (h)",
            "Mean CS Stops", "Median CS Stops",
            "Mean Total HoS Stops", "Median Total HoS Stops",
            "Mean Sync Events", "Median Sync Events",
            "Mean Sync %", "Mean Idle Time Savings (h)",
        ],
        "Full Recharge": [
            merged["time_full_h"].mean(),
            merged["time_full_h"].median(),
            merged["time_full_h"].std(),
            merged["cs_stops_full"].mean(),
            merged["cs_stops_full"].median(),
            merged["total_hos_stops_full"].mean(),
            merged["total_hos_stops_full"].median(),
            merged["sync_events_full"].mean(),
            merged["sync_events_full"].median(),
            merged["sync_pct_full"].mean(),
            merged["idle_time_savings_full_h"].mean(),
        ],
        "Partial Recharge": [
            merged["time_partial_h"].mean(),
            merged["time_partial_h"].median(),
            merged["time_partial_h"].std(),
            merged["cs_stops_partial"].mean(),
            merged["cs_stops_partial"].median(),
            merged["total_hos_stops_partial"].mean(),
            merged["total_hos_stops_partial"].median(),
            merged["sync_events_partial"].mean(),
            merged["sync_events_partial"].median(),
            merged["sync_pct_partial"].mean(),
            merged["idle_time_savings_partial_h"].mean(),
        ],
        "Greedy": [
            merged["time_greedy_h"].mean(),
            merged["time_greedy_h"].median(),
            merged["time_greedy_h"].std(),
            merged["cs_stops_greedy"].mean(),
            merged["cs_stops_greedy"].median(),
            merged["total_hos_stops_greedy"].mean(),
            merged["total_hos_stops_greedy"].median(),
            merged["sync_events_greedy"].mean(),
            merged["sync_events_greedy"].median(),
            merged["sync_pct_greedy"].mean(),
            merged["idle_time_savings_greedy_h"].mean(),
        ],
    })
    summary_overall.to_csv(out_dir / "table1_overall_summary.csv", index=False)
    
    # ===== TABLE 2: Summary by Route Class =====
    route_class_summary = []
    for route_class in ["short", "med", "long"]:
        subset = merged[merged["route_class"] == route_class]
        if len(subset) == 0:
            continue
        route_class_summary.append({
            "Route_Class": route_class,
            "Count": len(subset),
            "Mean_Time_Full": subset["time_full_h"].mean(),
            "Mean_Time_Partial": subset["time_partial_h"].mean(),
            "Mean_Time_Greedy": subset["time_greedy_h"].mean(),
            "Mean_CS_Full": subset["cs_stops_full"].mean(),
            "Mean_CS_Partial": subset["cs_stops_partial"].mean(),
            "Mean_CS_Greedy": subset["cs_stops_greedy"].mean(),
            "Mean_Sync_Full": subset["sync_events_full"].mean(),
            "Mean_Sync_Partial": subset["sync_events_partial"].mean(),
            "Mean_Sync_Greedy": subset["sync_events_greedy"].mean(),
            "Mean_Pct_Improvement_Partial": subset["pct_improvement_partial_vs_full"].mean(),
            "Mean_Pct_Improvement_Greedy": subset["pct_improvement_greedy_vs_full"].mean(),
        })
    
    df_route = pd.DataFrame(route_class_summary)
    df_route.to_csv(out_dir / "table2_summary_by_route_class.csv", index=False)
    
    # ===== TABLE 3: Summary by Allocation Type =====
    allocation_summary = []
    for alloc in ["Balanced", "Unbalanced", "N/A"]:
        subset = merged[merged["allocation"] == alloc]
        if len(subset) == 0:
            continue
        allocation_summary.append({
            "Allocation": alloc,
            "Count": len(subset),
            "Mean_Time_Full": subset["time_full_h"].mean(),
            "Mean_Time_Partial": subset["time_partial_h"].mean(),
            "Mean_Time_Greedy": subset["time_greedy_h"].mean(),
            "Mean_Pct_Improvement_Partial": subset["pct_improvement_partial_vs_full"].mean(),
            "Mean_Pct_Improvement_Greedy": subset["pct_improvement_greedy_vs_full"].mean(),
            "Mean_CS_Full": subset["cs_stops_full"].mean(),
            "Mean_CS_Partial": subset["cs_stops_partial"].mean(),
            "Mean_CS_Greedy": subset["cs_stops_greedy"].mean(),
        })
    
    df_alloc = pd.DataFrame(allocation_summary)
    df_alloc.to_csv(out_dir / "table3_summary_by_allocation.csv", index=False)
    
    # ===== TABLE 4: Synchronization Impact Analysis =====
    sync_analysis = []
    for route_class in ["short", "med", "long"]:
        subset = merged[merged["route_class"] == route_class]
        if len(subset) == 0:
            continue
        sync_analysis.append({
            "Route_Class": route_class,
            "Mean_Sync_Events_Full": subset["sync_events_full"].mean(),
            "Mean_Sync_Events_Partial": subset["sync_events_partial"].mean(),
            "Mean_Sync_Events_Greedy": subset["sync_events_greedy"].mean(),
            "Mean_Sync_Pct_Full": subset["sync_pct_full"].mean(),
            "Mean_Sync_Pct_Partial": subset["sync_pct_partial"].mean(),
            "Mean_Sync_Pct_Greedy": subset["sync_pct_greedy"].mean(),
            "Mean_Idle_Time_Saved_Full_h": subset["idle_time_savings_full_h"].mean(),
            "Mean_Idle_Time_Saved_Partial_h": subset["idle_time_savings_partial_h"].mean(),
        })
    
    df_sync = pd.DataFrame(sync_analysis)
    df_sync.to_csv(out_dir / "table4_synchronization_impact.csv", index=False)
    
    # ===== TABLE 5: Detailed Instance Comparison =====
    # Keep all computed metrics for detailed analysis
    detailed_cols = [
        "instance_id", "route_class", "clusters", "customers", "allocation",
        "time_full_h", "time_partial_h", "time_greedy_h",
        "pct_improvement_partial_vs_full", "pct_improvement_greedy_vs_full", "pct_improvement_greedy_vs_partial",
        "cs_stops_full", "cs_stops_partial", "cs_stops_greedy",
        "delta_cs_partial_minus_full", "delta_cs_greedy_minus_full",
        "total_hos_stops_full", "total_hos_stops_partial", "total_hos_stops_greedy",
        "sync_events_full", "sync_events_partial", "sync_events_greedy",
        "sync_pct_full", "sync_pct_partial", "sync_pct_greedy",
        "idle_time_savings_full_h", "idle_time_savings_partial_h",
    ]
    merged[detailed_cols].to_csv(out_dir / "table5_detailed_instance_comparison.csv", index=False)


def create_comparison_figures(merged: pd.DataFrame, out_dir: Path):
    """Create comprehensive comparison figures."""
    
    # ===== FIGURE 1: Per-instance total time comparison (existing, keep) =====
    plt.figure(figsize=(14, 7))
    x = range(len(merged))
    width = 0.25
    plt.bar([i - width for i in x], merged["time_full_h"], width=width, label="Full Recharge", alpha=0.8)
    plt.bar(x, merged["time_partial_h"], width=width, label="Partial Recharge", alpha=0.8)
    plt.bar([i + width for i in x], merged["time_greedy_h"], width=width, label="Greedy", alpha=0.8)
    plt.xticks(x, merged["instance_id"], rotation=90, fontsize=7)
    plt.ylabel("Total route time (hours)", fontsize=11)
    plt.title("Base-Scenario: Total Route Time Comparison per Instance", fontsize=13, fontweight='bold')
    plt.legend(fontsize=10)
    plt.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / "figure1_total_time_per_instance.png", dpi=200, bbox_inches='tight')
    plt.close()
    
    # ===== FIGURE 2: Time improvement percentages (box plot) =====
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    
    # Left: Partial vs Full, Greedy vs Full
    data1 = [merged["pct_improvement_partial_vs_full"], merged["pct_improvement_greedy_vs_full"]]
    axes[0].boxplot(data1, labels=["Partial vs Full", "Greedy vs Full"])
    axes[0].axhline(y=0, color='r', linestyle='--', alpha=0.5)
    axes[0].set_ylabel("Time Improvement (%)", fontsize=11)
    axes[0].set_title("Time Improvement vs Full Recharge", fontsize=12, fontweight='bold')
    axes[0].grid(axis='y', alpha=0.3)
    
    # Right: Greedy vs Partial
    axes[1].boxplot([merged["pct_improvement_greedy_vs_partial"]], labels=["Greedy vs Partial"])
    axes[1].axhline(y=0, color='r', linestyle='--', alpha=0.5)
    axes[1].set_ylabel("Time Improvement (%)", fontsize=11)
    axes[1].set_title("Time Improvement: Greedy vs Partial", fontsize=12, fontweight='bold')
    axes[1].grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(out_dir / "figure2_time_improvement_boxplots.png", dpi=200, bbox_inches='tight')
    plt.close()
    
    # ===== FIGURE 3: Comparison by Route Class =====
    route_classes = ["short", "med", "long"]
    x_pos = np.arange(len(route_classes))
    width = 0.25
    
    means_full = [merged[merged["route_class"] == rc]["time_full_h"].mean() for rc in route_classes]
    means_partial = [merged[merged["route_class"] == rc]["time_partial_h"].mean() for rc in route_classes]
    means_greedy = [merged[merged["route_class"] == rc]["time_greedy_h"].mean() for rc in route_classes]
    
    plt.figure(figsize=(10, 6))
    plt.bar(x_pos - width, means_full, width, label="Full Recharge", alpha=0.8)
    plt.bar(x_pos, means_partial, width, label="Partial Recharge", alpha=0.8)
    plt.bar(x_pos + width, means_greedy, width, label="Greedy", alpha=0.8)
    plt.xlabel("Route Class", fontsize=11)
    plt.ylabel("Mean Total Time (hours)", fontsize=11)
    plt.title("Mean Total Time by Route Class", fontsize=13, fontweight='bold')
    plt.xticks(x_pos, [rc.capitalize() for rc in route_classes])
    plt.legend(fontsize=10)
    plt.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / "figure3_time_by_route_class.png", dpi=200, bbox_inches='tight')
    plt.close()
    
    # ===== FIGURE 4: Comparison by Allocation Type =====
    alloc_types = ["Balanced", "Unbalanced"]
    x_pos = np.arange(len(alloc_types))
    
    means_full_bal = merged[merged["allocation"] == "Balanced"]["time_full_h"].mean()
    means_full_unbal = merged[merged["allocation"] == "Unbalanced"]["time_full_h"].mean()
    means_partial_bal = merged[merged["allocation"] == "Balanced"]["time_partial_h"].mean()
    means_partial_unbal = merged[merged["allocation"] == "Unbalanced"]["time_partial_h"].mean()
    means_greedy_bal = merged[merged["allocation"] == "Balanced"]["time_greedy_h"].mean()
    means_greedy_unbal = merged[merged["allocation"] == "Unbalanced"]["time_greedy_h"].mean()
    
    plt.figure(figsize=(10, 6))
    plt.bar(x_pos - width, [means_full_bal, means_full_unbal], width, label="Full Recharge", alpha=0.8)
    plt.bar(x_pos, [means_partial_bal, means_partial_unbal], width, label="Partial Recharge", alpha=0.8)
    plt.bar(x_pos + width, [means_greedy_bal, means_greedy_unbal], width, label="Greedy", alpha=0.8)
    plt.xlabel("Allocation Type", fontsize=11)
    plt.ylabel("Mean Total Time (hours)", fontsize=11)
    plt.title("Mean Total Time by Allocation Type", fontsize=13, fontweight='bold')
    plt.xticks(x_pos, alloc_types)
    plt.legend(fontsize=10)
    plt.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / "figure4_time_by_allocation.png", dpi=200, bbox_inches='tight')
    plt.close()
    
    # ===== FIGURE 5: Charging Stops Comparison =====
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    
    # Left: Mean CS stops by route class
    route_classes = ["short", "med", "long"]
    x_pos = np.arange(len(route_classes))
    width_bar = 0.25
    
    cs_full = [merged[merged["route_class"] == rc]["cs_stops_full"].mean() for rc in route_classes]
    cs_partial = [merged[merged["route_class"] == rc]["cs_stops_partial"].mean() for rc in route_classes]
    cs_greedy = [merged[merged["route_class"] == rc]["cs_stops_greedy"].mean() for rc in route_classes]
    
    axes[0].bar(x_pos - width_bar, cs_full, width_bar, label="Full", alpha=0.8)
    axes[0].bar(x_pos, cs_partial, width_bar, label="Partial", alpha=0.8)
    axes[0].bar(x_pos + width_bar, cs_greedy, width_bar, label="Greedy", alpha=0.8)
    axes[0].set_xlabel("Route Class", fontsize=10)
    axes[0].set_ylabel("Mean Charging Stops", fontsize=10)
    axes[0].set_title("Mean CS Stops by Route Class", fontsize=11, fontweight='bold')
    axes[0].set_xticks(x_pos)
    axes[0].set_xticklabels([rc.capitalize() for rc in route_classes])
    axes[0].legend(fontsize=9)
    axes[0].grid(axis='y', alpha=0.3)
    
    # Right: Scatter plot: Time vs CS Stops
    axes[1].scatter(merged["cs_stops_full"], merged["time_full_h"], alpha=0.6, label="Full", s=50)
    axes[1].scatter(merged["cs_stops_partial"], merged["time_partial_h"], alpha=0.6, label="Partial", s=50)
    axes[1].scatter(merged["cs_stops_greedy"], merged["time_greedy_h"], alpha=0.6, label="Greedy", s=50)
    axes[1].set_xlabel("Number of Charging Stops", fontsize=10)
    axes[1].set_ylabel("Total Time (hours)", fontsize=10)
    axes[1].set_title("Time vs Charging Stops", fontsize=11, fontweight='bold')
    axes[1].legend(fontsize=9)
    axes[1].grid(alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(out_dir / "figure5_charging_stops_analysis.png", dpi=200, bbox_inches='tight')
    plt.close()
    
    # ===== FIGURE 6: Synchronization Impact Analysis =====
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # Top-left: Sync events by route class
    route_classes = ["short", "med", "long"]
    x_pos = np.arange(len(route_classes))
    
    sync_full = [merged[merged["route_class"] == rc]["sync_events_full"].mean() for rc in route_classes]
    sync_partial = [merged[merged["route_class"] == rc]["sync_events_partial"].mean() for rc in route_classes]
    sync_greedy = [merged[merged["route_class"] == rc]["sync_events_greedy"].mean() for rc in route_classes]
    
    axes[0, 0].bar(x_pos - width, sync_full, width, label="Full", alpha=0.8)
    axes[0, 0].bar(x_pos, sync_partial, width, label="Partial", alpha=0.8)
    axes[0, 0].bar(x_pos + width, sync_greedy, width, label="Greedy", alpha=0.8)
    axes[0, 0].set_xlabel("Route Class", fontsize=10)
    axes[0, 0].set_ylabel("Mean Sync Events", fontsize=10)
    axes[0, 0].set_title("Synchronized Events by Route Class", fontsize=11, fontweight='bold')
    axes[0, 0].set_xticks(x_pos)
    axes[0, 0].set_xticklabels([rc.capitalize() for rc in route_classes])
    axes[0, 0].legend(fontsize=9)
    axes[0, 0].grid(axis='y', alpha=0.3)
    
    # Top-right: Sync percentage
    sync_pct_full = [merged[merged["route_class"] == rc]["sync_pct_full"].mean() for rc in route_classes]
    sync_pct_partial = [merged[merged["route_class"] == rc]["sync_pct_partial"].mean() for rc in route_classes]
    
    axes[0, 1].bar(x_pos - width/2, sync_pct_full, width, label="Full", alpha=0.8)
    axes[0, 1].bar(x_pos + width/2, sync_pct_partial, width, label="Partial", alpha=0.8)
    axes[0, 1].set_xlabel("Route Class", fontsize=10)
    axes[0, 1].set_ylabel("Mean Sync %", fontsize=10)
    axes[0, 1].set_title("Synchronization Percentage", fontsize=11, fontweight='bold')
    axes[0, 1].set_xticks(x_pos)
    axes[0, 1].set_xticklabels([rc.capitalize() for rc in route_classes])
    axes[0, 1].set_ylim([0, 105])
    axes[0, 1].legend(fontsize=9)
    axes[0, 1].grid(axis='y', alpha=0.3)
    
    # Bottom-left: Idle time savings
    idle_full = [merged[merged["route_class"] == rc]["idle_time_savings_full_h"].mean() for rc in route_classes]
    idle_partial = [merged[merged["route_class"] == rc]["idle_time_savings_partial_h"].mean() for rc in route_classes]
    
    axes[1, 0].bar(x_pos - width/2, idle_full, width, label="Full", alpha=0.8)
    axes[1, 0].bar(x_pos + width/2, idle_partial, width, label="Partial", alpha=0.8)
    axes[1, 0].set_xlabel("Route Class", fontsize=10)
    axes[1, 0].set_ylabel("Mean Idle Time Saved (h)", fontsize=10)
    axes[1, 0].set_title("Time Savings from Synchronization", fontsize=11, fontweight='bold')
    axes[1, 0].set_xticks(x_pos)
    axes[1, 0].set_xticklabels([rc.capitalize() for rc in route_classes])
    axes[1, 0].legend(fontsize=9)
    axes[1, 0].grid(axis='y', alpha=0.3)
    
    # Bottom-right: HoS stops comparison
    hos_full = [merged[merged["route_class"] == rc]["total_hos_stops_full"].mean() for rc in route_classes]
    hos_partial = [merged[merged["route_class"] == rc]["total_hos_stops_partial"].mean() for rc in route_classes]
    hos_greedy = [merged[merged["route_class"] == rc]["total_hos_stops_greedy"].mean() for rc in route_classes]
    
    axes[1, 1].bar(x_pos - width, hos_full, width, label="Full", alpha=0.8)
    axes[1, 1].bar(x_pos, hos_partial, width, label="Partial", alpha=0.8)
    axes[1, 1].bar(x_pos + width, hos_greedy, width, label="Greedy", alpha=0.8)
    axes[1, 1].set_xlabel("Route Class", fontsize=10)
    axes[1, 1].set_ylabel("Mean Total HoS Stops", fontsize=10)
    axes[1, 1].set_title("HoS Stops (Breaks + Rests)", fontsize=11, fontweight='bold')
    axes[1, 1].set_xticks(x_pos)
    axes[1, 1].set_xticklabels([rc.capitalize() for rc in route_classes])
    axes[1, 1].legend(fontsize=9)
    axes[1, 1].grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(out_dir / "figure6_synchronization_impact.png", dpi=200, bbox_inches='tight')
    plt.close()
    
    # ===== FIGURE 7: Improvement Heatmap by Route Class and Allocation =====
    # Create pivot table for percentage improvement
    pivot_data = merged.pivot_table(
        values='pct_improvement_partial_vs_full',
        index='route_class',
        columns='allocation',
        aggfunc='mean'
    )
    
    plt.figure(figsize=(8, 6))
    im = plt.imshow(pivot_data.values, cmap='RdYlGn', aspect='auto')
    plt.colorbar(im, label='Time Improvement (%)')
    plt.xticks(range(len(pivot_data.columns)), pivot_data.columns)
    plt.yticks(range(len(pivot_data.index)), [rc.capitalize() for rc in pivot_data.index])
    plt.xlabel("Allocation Type", fontsize=11)
    plt.ylabel("Route Class", fontsize=11)
    plt.title("Partial vs Full: Mean Time Improvement (%)", fontsize=13, fontweight='bold')
    
    # Add text annotations
    for i in range(len(pivot_data.index)):
        for j in range(len(pivot_data.columns)):
            text = plt.text(j, i, f'{pivot_data.iloc[i, j]:.2f}%',
                          ha="center", va="center", color="black", fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(out_dir / "figure7_improvement_heatmap_partial.png", dpi=200, bbox_inches='tight')
    plt.close()
    
    # Same for Greedy
    pivot_data_greedy = merged.pivot_table(
        values='pct_improvement_greedy_vs_full',
        index='route_class',
        columns='allocation',
        aggfunc='mean'
    )
    
    plt.figure(figsize=(8, 6))
    im = plt.imshow(pivot_data_greedy.values, cmap='RdYlGn', aspect='auto')
    plt.colorbar(im, label='Time Improvement (%)')
    plt.xticks(range(len(pivot_data_greedy.columns)), pivot_data_greedy.columns)
    plt.yticks(range(len(pivot_data_greedy.index)), [rc.capitalize() for rc in pivot_data_greedy.index])
    plt.xlabel("Allocation Type", fontsize=11)
    plt.ylabel("Route Class", fontsize=11)
    plt.title("Greedy vs Full: Mean Time Improvement (%)", fontsize=13, fontweight='bold')
    
    for i in range(len(pivot_data_greedy.index)):
        for j in range(len(pivot_data_greedy.columns)):
            text = plt.text(j, i, f'{pivot_data_greedy.iloc[i, j]:.2f}%',
                          ha="center", va="center", color="black", fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(out_dir / "figure8_improvement_heatmap_greedy.png", dpi=200, bbox_inches='tight')
    plt.close()


def main() -> None:
    """Main execution function."""
    out_dir = ROOT_DIR / "Results_basescenario"
    out_dir.mkdir(exist_ok=True)
    
    print("Loading result files...")
    df_partial = load_partial_results()
    df_full = load_full_results()
    df_greedy = load_greedy_results()
    
    print("Merging datasets...")
    # Merge on instance_id
    merged = (
        df_partial.merge(df_full, on="instance_id", how="inner")
        .merge(df_greedy, on="instance_id", how="inner")
        .sort_values("instance_id")
    )
    
    print("Computing comparative metrics...")
    merged = compute_comparative_metrics(merged)
    
    print("Creating summary tables...")
    create_summary_tables(merged, out_dir)
    
    print("Creating comparison figures...")
    create_comparison_figures(merged, out_dir)
    
    # Save full merged dataset with all metrics
    merged.to_csv(out_dir / "complete_merged_results_with_metrics.csv", index=False)
    
    print(f"\n{'='*80}")
    print(f"Comprehensive analysis completed!")
    print(f"Results saved to: {out_dir}")
    print(f"\nGenerated files:")
    print(f"  Tables: 5 summary tables (CSV)")
    print(f"  Figures: 8 comparison figures (PNG)")
    print(f"  Complete dataset: complete_merged_results_with_metrics.csv")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
