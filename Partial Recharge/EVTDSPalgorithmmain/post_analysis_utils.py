import os
import json
import glob
from typing import Optional, Tuple, List, Dict

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns


class PerformanceFeasibilityOverview:
	"""Implements feasibility and route-time visualizations required for the thesis.

	Outputs (saved under Results/Post_Analysis/):
	- feasibility_heatmaps.png: Heatmaps of feasibility (%) by CS interval (x) and battery (y),
	  faceted by consumption (rows) and charging power (columns: 350, 1000)
	- feasibility_frontiers.png: Overlay lines of minimum battery to reach ≥90% feasibility vs CS interval,
	  per consumption (rows), with lines for CP in {350, 1000}
	- time_boxplot_by_cs_interval.png: Boxplot of feasible completion time vs CS interval
	- time_boxplot_by_battery.png: Boxplot of feasible completion time vs battery
	- time_boxplot_by_consumption.png: Boxplot of feasible completion time vs consumption
	- time_boxplot_by_cp.png: Boxplot of feasible completion time vs charging power
	- interaction_battery_cs.png: Median completion time vs CS interval with one line per battery,
	  faceted by consumption (rows) and CP (columns)
	- interaction_cp_battery.png: Median completion time vs CP with one line per battery,
	  faceted by consumption (rows)
	- per_instance_times.png: Small multiple boxplots of completion time per instance, colored by consumption
	- paired_slope_greedy_vs_labeling.png: Slope plot connecting greedy vs labeling times per scenario
	- improvement_by_cs_interval.png: Violin/box of % improvement grouped by CS interval
	- per_instance_feasibility_grid.png: Per-instance heatmaps (consumption × CP) of feasibility rates
	- per_instance_improvement_violin.png: Per-instance violin of % improvement (labeling vs greedy)
	- paired_slope_per_instance_*.png: One slope plot per instance comparing greedy vs labeling
	- counts_mean_bars.png: Mean counts (sync, CS stops, breaks, rests) labeling vs greedy
	- counts_delta_by_consumption.png: Violin/box of deltas (labeling - greedy) by consumption
	- sync_delta_vs_time_improvement.png: Scatter of sync delta vs % time improvement
	- mixedlm_summary.txt: Mixed-effects model (random intercept per instance) summary
	- anova_effects.csv: Factorial ANOVA with partial eta^2
	- anova_effects_bootstrap_ci.csv: Bootstrap 95% CIs for partial eta^2 (clustered by instance)
	- pairwise_effects_aggregated.csv: Cliff's delta and Hodges–Lehmann shifts per factor (aggregated)
	- pairwise_effects_by_instance.csv: Same metrics per instance
	- sensitivity_main_effects_by_instance.csv: Per-instance medians by factor levels (for diagnostics)
	"""

	OUTPUT_DIR = os.path.join("Results", "Post_Analysis")

	def __init__(self, results_path: Optional[str] = None) -> None:
		self.results_path = results_path or self._autodetect_latest_results()
		if self.results_path is None:
			raise FileNotFoundError(
				"No enhanced results file found. Expected 'Results/enhanced_results_*.csv|json'."
			)
		self.df = self._load_and_normalize(self.results_path)
		self._ensure_output_dir()

	def _ensure_output_dir(self) -> None:
		if not os.path.exists(self.OUTPUT_DIR):
			os.makedirs(self.OUTPUT_DIR, exist_ok=True)

	def _autodetect_latest_results(self) -> Optional[str]:
		candidates = []
		for pattern in [
			os.path.join("Results", "enhanced_results_*.csv"),
			os.path.join("Results", "enhanced_results_*.json"),
		]:
			candidates.extend(glob.glob(pattern))
		if not candidates:
			return None
		candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
		return candidates[0]

	def _load_json_results(self, path: str) -> pd.DataFrame:
		with open(path, "r") as f:
			raw = json.load(f)
		if isinstance(raw, dict) and "results" in raw:
			data = raw["results"]
		elif isinstance(raw, list):
			data = raw
		else:
			raise ValueError("Unsupported JSON structure for results file")
		return pd.DataFrame(data)

	def _load_and_normalize(self, path: str) -> pd.DataFrame:
		if path.endswith(".csv"):
			df = pd.read_csv(path)
		elif path.endswith(".json"):
			df = self._load_json_results(path)
		else:
			raise ValueError("Results file must be CSV or JSON")

		# Normalize field names/types expected by this overview
		df = df.copy()

		# Feasible -> boolean
		if "feasible" in df.columns:
			df["feasible"] = df["feasible"].apply(
				lambda v: True if v in (True, "True", "true", 1, "1") else False
			)
		else:
			df["feasible"] = False

		# Total route time in hours (prefer hours; derive from minutes if needed)
		if "total_route_time_hours" in df.columns:
			df["total_route_time_hours"] = pd.to_numeric(
				df["total_route_time_hours"], errors="coerce"
			)
		elif "total_route_time_minutes" in df.columns:
			df["total_route_time_hours"] = pd.to_numeric(
				df["total_route_time_minutes"], errors="coerce"
			) / 60.0
		else:
			df["total_route_time_hours"] = pd.NA

		# Numeric fields
		for col in [
			"battery_capacity_kWh",
			"charging_station_interval_km",
			"charging_power_kW",
			"energy_consumption_rate_kWh_per_km",
			"number_of_customer_locations",
			"number_of_cs_stops",
			"number_of_breaks",
			"number_of_rests",
			"number_of_synchronized_events",
			"number_of_unsynchronized_charging_events",
		]:
			if col in df.columns:
				df[col] = pd.to_numeric(df[col], errors="coerce")

		# Identifiers
		for col in ["instance_id", "test_bed_id"]:
			if col not in df.columns:
				df[col] = pd.NA

		return df

	# ---------- Feasibility Aggregation ----------
	def _feasibility_group(self) -> pd.DataFrame:
		required = [
			"battery_capacity_kWh",
			"charging_station_interval_km",
			"energy_consumption_rate_kWh_per_km",
			"charging_power_kW",
		]
		for c in required:
			if c not in self.df.columns:
				raise KeyError(f"Missing required column: {c}")
		grp = (
			self.df.groupby(required + (["instance_id"] if "instance_id" in self.df.columns else []), dropna=False)
			.agg(total_scenarios=("feasible", "size"), feasible_scenarios=("feasible", "sum"))
			.reset_index()
		)
		grp["feasibility_rate"] = grp["feasible_scenarios"] / grp["total_scenarios"]
		return grp

	# ---------- Paired Greedy vs Labeling Data ----------
	def _autodetect_latest_greedy(self) -> Optional[str]:
		candidates = glob.glob(os.path.join("Results", "Greedy_Scheduler_Results", "greedy_results_*.csv"))
		if not candidates:
			return None
		candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
		return candidates[0]

	def _prepare_paired_data(self) -> Optional[pd.DataFrame]:
		greedy_path = self._autodetect_latest_greedy()
		if greedy_path is None:
			return None
		g = pd.read_csv(greedy_path)
		# Normalize names
		g = g.rename(
			columns={
				"distance_per_cs": "charging_station_interval_km",
				"battery_capacity": "battery_capacity_kWh",
				"charging_power": "charging_power_kW",
				"consumption_rate": "energy_consumption_rate_kWh_per_km",
				"total_time": "greedy_time_hours",
				"num_charges": "greedy_cs_stops",
				"num_breaks": "greedy_breaks",
				"num_rests": "greedy_rests",
				"num_synchronized_events": "greedy_sync_events",
			}
		)
		# Cast keys to comparable types
		for col in [
			"instance_id",
			"charging_station_interval_km",
			"battery_capacity_kWh",
			"charging_power_kW",
			"greedy_cs_stops",
			"greedy_breaks",
			"greedy_rests",
			"greedy_sync_events",
		]:
			if col in g.columns:
				g[col] = pd.to_numeric(g[col], errors="coerce")
		if "energy_consumption_rate_kWh_per_km" in g.columns:
			g["energy_consumption_rate_kWh_per_km"] = pd.to_numeric(g["energy_consumption_rate_kWh_per_km"], errors="coerce").round(2)
		# Prepare labeling side (pick best feasible time per scenario key)
		k = [
			"instance_id",
			"charging_station_interval_km",
			"battery_capacity_kWh",
			"charging_power_kW",
			"energy_consumption_rate_kWh_per_km",
		]
		lab = self.df[self.df["feasible"] & self.df["total_route_time_hours"].notna()].copy()
		for col in k:
			if col in lab.columns:
				lab[col] = pd.to_numeric(lab[col], errors="coerce")
		lab["energy_consumption_rate_kWh_per_km"] = lab["energy_consumption_rate_kWh_per_km"].round(2)
		# Aggregate labeling counts for the best-time scenario
		lab_best_time = lab.groupby(k)["total_route_time_hours"].min().reset_index().rename(columns={"total_route_time_hours": "labeling_time_hours"})
		lab_counts = lab.groupby(k)[
			["number_of_cs_stops", "number_of_breaks", "number_of_rests", "number_of_synchronized_events"]
		].mean().reset_index().rename(
			columns={
				"number_of_cs_stops": "labeling_cs_stops",
				"number_of_breaks": "labeling_breaks",
				"number_of_rests": "labeling_rests",
				"number_of_synchronized_events": "labeling_sync_events",
			}
		)
		lab_best = pd.merge(lab_best_time, lab_counts, on=k, how="left")
		# Merge
		merged = pd.merge(g, lab_best, on=k, how="inner")
		if merged.empty:
			return None
		merged["percent_improvement"] = (merged["greedy_time_hours"] - merged["labeling_time_hours"]) / merged["greedy_time_hours"]
		# Deltas (labeling - greedy)
		for pair in [
			("labeling_cs_stops", "greedy_cs_stops", "delta_cs_stops"),
			("labeling_breaks", "greedy_breaks", "delta_breaks"),
			("labeling_rests", "greedy_rests", "delta_rests"),
			("labeling_sync_events", "greedy_sync_events", "delta_sync_events"),
		]:
			if pair[0] in merged.columns and pair[1] in merged.columns:
				merged[pair[2]] = merged[pair[0]] - merged[pair[1]]
		return merged

	# ---------- Count Comparison Figures ----------
	def save_counts_mean_bars(self) -> Optional[str]:
		merged = self._prepare_paired_data()
		if merged is None or merged.empty:
			return None
		# Compute means
		rows = []
		metrics = [
			("Sync events", "greedy_sync_events", "labeling_sync_events"),
			("CS stops", "greedy_cs_stops", "labeling_cs_stops"),
			("Breaks", "greedy_breaks", "labeling_breaks"),
			("Rests", "greedy_rests", "labeling_rests"),
		]
		for label, g_col, l_col in metrics:
			if g_col in merged.columns and l_col in merged.columns:
				rows.append({"metric": label, "approach": "Greedy", "mean": merged[g_col].mean()})
				rows.append({"metric": label, "approach": "Labeling", "mean": merged[l_col].mean()})
		comp = pd.DataFrame(rows)
		plt.figure(figsize=(8, 5))
		sns.barplot(data=comp, x="metric", y="mean", hue="approach", palette=["#f58518", "#4c78a8"]) 
		plt.xlabel("")
		plt.ylabel("Mean count")
		plt.title("Mean counts: Labeling vs Greedy")
		out_path = os.path.join(self.OUTPUT_DIR, "counts_mean_bars.png")
		plt.tight_layout()
		plt.savefig(out_path, dpi=300)
		plt.close()
		return out_path

	def save_counts_delta_by_consumption(self) -> Optional[str]:
		merged = self._prepare_paired_data()
		if merged is None or merged.empty or "energy_consumption_rate_kWh_per_km" not in merged.columns:
			return None
		melt = []
		for col in ["delta_sync_events", "delta_cs_stops", "delta_breaks", "delta_rests"]:
			if col in merged.columns:
				m = merged[["energy_consumption_rate_kWh_per_km", col]].copy()
				m = m.rename(columns={col: "delta"})
				m["metric"] = col.replace("delta_", "")
				melt.append(m)
		if not melt:
			return None
		melt_df = pd.concat(melt, ignore_index=True)
		plt.figure(figsize=(9, 5))
		sns.violinplot(data=melt_df, x="energy_consumption_rate_kWh_per_km", y="delta", hue="metric", split=True)
		plt.xlabel("Consumption (kWh/km)")
		plt.ylabel("Delta (Labeling - Greedy)")
		plt.title("Count deltas by consumption")
		out_path = os.path.join(self.OUTPUT_DIR, "counts_delta_by_consumption.png")
		plt.tight_layout()
		plt.savefig(out_path, dpi=300)
		plt.close()
		return out_path

	def save_sync_delta_vs_time_improvement(self) -> Optional[str]:
		merged = self._prepare_paired_data()
		if merged is None or merged.empty or "delta_sync_events" not in merged.columns:
			return None
		plt.figure(figsize=(7, 5))
		sns.scatterplot(data=merged, x="delta_sync_events", y="percent_improvement", hue="energy_consumption_rate_kWh_per_km", palette="viridis")
		plt.xlabel("Sync events delta (Labeling - Greedy)")
		plt.ylabel("% time improvement (Labeling vs Greedy)")
		plt.title("Sync delta vs time improvement")
		out_path = os.path.join(self.OUTPUT_DIR, "sync_delta_vs_time_improvement.png")
		plt.tight_layout()
		plt.savefig(out_path, dpi=300)
		plt.close()
		return out_path

	# ---------- Feasibility Visuals ----------
	def save_feasibility_heatmaps(self) -> Optional[str]:
		grp = self._feasibility_group()
		# Collapse over instances for the global heatmaps
		cols = [
			"battery_capacity_kWh",
			"charging_station_interval_km",
			"energy_consumption_rate_kWh_per_km",
			"charging_power_kW",
		]
		global_grp = (
			grp.groupby(cols, dropna=False)
			.agg(feasibility_rate=("feasibility_rate", "mean"))
			.reset_index()
		)
		consumptions = sorted(global_grp["energy_consumption_rate_kWh_per_km"].dropna().unique())
		cps = [x for x in [350, 1000] if x in set(global_grp["charging_power_kW"].dropna().unique())]
		if not consumptions or not cps:
			return None
		fig, axes = plt.subplots(len(consumptions), len(cps), figsize=(5 * len(cps), 4 * len(consumptions)), squeeze=False)
		for r, cons in enumerate(consumptions):
			for c, cp in enumerate(cps):
				panel = global_grp[(global_grp["energy_consumption_rate_kWh_per_km"] == cons) & (global_grp["charging_power_kW"] == cp)].copy()
				if panel.empty:
					axes[r, c].axis("off")
					continue
				pivot = panel.pivot_table(
					index="battery_capacity_kWh",
					columns="charging_station_interval_km",
					values="feasibility_rate",
					aggfunc="mean",
				)
				sns.heatmap(
					pivot.sort_index(ascending=True),
					ax=axes[r, c],
					cmap="RdYlGn",
					vmin=0,
					vmax=1,
					cbar=r == 0 and c == len(cps) - 1,
					cbar_kws={"label": "Feasibility (%)"},
					annot=False,
				)
				axes[r, c].set_title(f"Consumption={cons}, CP={cp}")
				axes[r, c].set_xlabel("CS interval (km)")
				axes[r, c].set_ylabel("Battery (kWh)")
		plt.suptitle("Feasibility (%) across CS spacing and battery size, by consumption and CP")
		out_path = os.path.join(self.OUTPUT_DIR, "feasibility_heatmaps.png")
		plt.tight_layout(rect=[0, 0, 1, 0.96])
		plt.savefig(out_path, dpi=300)
		plt.close()
		return out_path

	def save_per_instance_feasibility_grid(self, max_instances: int = 9) -> Optional[str]:
		grp = self._feasibility_group()
		if "instance_id" not in grp.columns or grp.empty:
			return None
		instances = list(pd.Series(grp["instance_id"].dropna().unique()).sort_values())
		if not instances:
			return None
		instances = instances[:max_instances]
		cols = 3
		rows = (len(instances) + cols - 1) // cols
		fig, axes = plt.subplots(rows, cols, figsize=(5 * cols, 4 * rows), squeeze=False)
		for idx, inst in enumerate(instances):
			r = idx // cols
			c = idx % cols
			panel = grp[grp["instance_id"].astype(str) == str(inst)].copy()
			if panel.empty:
				axes[r, c].axis("off")
				continue
			# Aggregate feasibility over CS/battery to consumption x CP grid for compact per-instance summary
			agg = (
				panel.groupby(["energy_consumption_rate_kWh_per_km", "charging_power_kW"])['feasibility_rate']
				.mean()
				.reset_index()
			)
			pivot = agg.pivot_table(
				index="energy_consumption_rate_kWh_per_km",
				columns="charging_power_kW",
				values="feasibility_rate",
				aggfunc="mean",
			)
			sns.heatmap(
				pivot.sort_index(ascending=True),
				ax=axes[r, c],
				cmap="RdYlGn",
				vmin=0,
				vmax=1,
				cbar=False,
				annot=True,
				fmt=".0%",
			)
			axes[r, c].set_title(f"Instance {inst}")
			axes[r, c].set_xlabel("Charging power (kW)")
			axes[r, c].set_ylabel("Consumption (kWh/km)")
		# Hide extra axes
		for j in range(len(instances), rows * cols):
			r = j // cols
			c = j % cols
			axes[r, c].axis("off")
		out_path = os.path.join(self.OUTPUT_DIR, "per_instance_feasibility_grid.png")
		plt.tight_layout()
		plt.savefig(out_path, dpi=300)
		plt.close()
		return out_path

	def save_feasibility_frontiers(self, threshold: float = 0.9) -> Optional[str]:
		grp = self._feasibility_group()
		consumptions = sorted(grp["energy_consumption_rate_kWh_per_km"].dropna().unique())
		cps = [x for x in [350, 1000] if x in set(grp["charging_power_kW"].dropna().unique())]
		if not consumptions or not cps:
			return None
		fig, axes = plt.subplots(len(consumptions), 1, figsize=(7, 4 * len(consumptions)), squeeze=False)
		for r, cons in enumerate(consumptions):
			ax = axes[r, 0]
			for cp in cps:
				panel = grp[(grp["energy_consumption_rate_kWh_per_km"] == cons) & (grp["charging_power_kW"] == cp)].copy()
				if panel.empty:
					continue
				# For each CS interval, find min battery with feas >= threshold
				rows = []
				for cs in sorted(panel["charging_station_interval_km"].unique()):
					p_cs = panel[panel["charging_station_interval_km"] == cs]
					p_cs = p_cs.sort_values("battery_capacity_kWh")
					cand = p_cs[p_cs["feasibility_rate"] >= threshold]
					min_batt = cand["battery_capacity_kWh"].min() if not cand.empty else None
					rows.append({"cs": cs, "min_battery": min_batt})
				frontier = pd.DataFrame(rows).dropna()
				if not frontier.empty:
					ax.plot(frontier["cs"], frontier["min_battery"], marker="o", label=f"CP={cp}")
			ax.set_title(f"Feasibility frontier (>= {int(threshold*100)}%) | Consumption={cons}")
			ax.set_xlabel("CS interval (km)")
			ax.set_ylabel("Minimum battery (kWh)")
			ax.legend()
		out_path = os.path.join(self.OUTPUT_DIR, "feasibility_frontiers.png")
		plt.tight_layout()
		plt.savefig(out_path, dpi=300)
		plt.close()
		return out_path

	# ---------- Route Time: Single-Factor Boxplots ----------
	def _save_time_boxplot(self, factor: str, filename: str, xlabel: str) -> Optional[str]:
		df = self.df[self.df["feasible"] & self.df["total_route_time_hours"].notna()].copy()
		if df.empty or factor not in df.columns:
			return None
		plt.figure(figsize=(8, 5))
		sns.boxplot(data=df, x=factor, y="total_route_time_hours", color="#4c78a8")
		plt.xlabel(xlabel)
		plt.ylabel("Completion time (hours)")
		plt.title(f"Completion time by {xlabel}")
		out_path = os.path.join(self.OUTPUT_DIR, filename)
		plt.tight_layout()
		plt.savefig(out_path, dpi=300)
		plt.close()
		return out_path

	def save_time_boxplots_by_factor(self) -> List[Optional[str]]:
		outputs = []
		outputs.append(self._save_time_boxplot("charging_station_interval_km", "time_boxplot_by_cs_interval.png", "CS interval (km)"))
		outputs.append(self._save_time_boxplot("battery_capacity_kWh", "time_boxplot_by_battery.png", "Battery (kWh)"))
		outputs.append(self._save_time_boxplot("energy_consumption_rate_kWh_per_km", "time_boxplot_by_consumption.png", "Consumption (kWh/km)"))
		outputs.append(self._save_time_boxplot("charging_power_kW", "time_boxplot_by_cp.png", "Charging power (kW)"))
		return outputs

	# ---------- Route Time: Two-Way Interaction Plots ----------
	def save_interaction_battery_cs(self) -> Optional[str]:
		df = self.df[self.df["feasible"] & self.df["total_route_time_hours"].notna()].copy()
		if df.empty:
			return None
		consumptions = sorted(df["energy_consumption_rate_kWh_per_km"].dropna().unique())
		cps = sorted(df["charging_power_kW"].dropna().unique())
		if not consumptions or not cps:
			return None
		fig, axes = plt.subplots(len(consumptions), len(cps), figsize=(5 * len(cps), 4 * len(consumptions)), squeeze=False)
		for r, cons in enumerate(consumptions):
			for c, cp in enumerate(cps):
				panel = df[(df["energy_consumption_rate_kWh_per_km"] == cons) & (df["charging_power_kW"] == cp)]
				if panel.empty:
					axes[r, c].axis("off")
					continue
				agg = panel.groupby(["charging_station_interval_km", "battery_capacity_kWh"])['total_route_time_hours'].median().reset_index()
				for batt, sub in agg.groupby("battery_capacity_kWh"):
					sub = sub.sort_values("charging_station_interval_km")
					axes[r, c].plot(sub["charging_station_interval_km"], sub["total_route_time_hours"], marker="o", label=f"Batt={int(batt)}")
				axes[r, c].set_title(f"Cons={cons}, CP={int(cp)}")
				axes[r, c].set_xlabel("CS interval (km)")
				axes[r, c].set_ylabel("Median time (h)")
				axes[r, c].legend(fontsize=8)
		out_path = os.path.join(self.OUTPUT_DIR, "interaction_battery_cs.png")
		plt.tight_layout()
		plt.savefig(out_path, dpi=300)
		plt.close()
		return out_path

	def save_interaction_cp_battery(self) -> Optional[str]:
		df = self.df[self.df["feasible"] & self.df["total_route_time_hours"].notna()].copy()
		if df.empty:
			return None
		consumptions = sorted(df["energy_consumption_rate_kWh_per_km"].dropna().unique())
		if not consumptions:
			return None
		fig, axes = plt.subplots(len(consumptions), 1, figsize=(7, 4 * len(consumptions)), squeeze=False)
		for r, cons in enumerate(consumptions):
			panel = df[df["energy_consumption_rate_kWh_per_km"] == cons]
			agg = panel.groupby(["charging_power_kW", "battery_capacity_kWh"])['total_route_time_hours'].median().reset_index()
			for batt, sub in agg.groupby("battery_capacity_kWh"):
				sub = sub.sort_values("charging_power_kW")
				axes[r, 0].plot(sub["charging_power_kW"], sub["total_route_time_hours"], marker="o", label=f"Batt={int(batt)}")
			axes[r, 0].set_title(f"Median time vs CP | Cons={cons}")
			axes[r, 0].set_xlabel("Charging power (kW)")
			axes[r, 0].set_ylabel("Median time (h)")
			axes[r, 0].legend(fontsize=8)
		out_path = os.path.join(self.OUTPUT_DIR, "interaction_cp_battery.png")
		plt.tight_layout()
		plt.savefig(out_path, dpi=300)
		plt.close()
		return out_path

	# ---------- Per-instance Small Multiples ----------
	def save_per_instance_small_multiples(self, max_instances: int = 12) -> Optional[str]:
		df = self.df[self.df["feasible"] & self.df["total_route_time_hours"].notna()].copy()
		if df.empty or "instance_id" not in df.columns:
			return None
		instances = list(pd.Series(df["instance_id"].dropna().unique()).sort_values())
		if not instances:
			return None
		instances = instances[:max_instances]
		cols = 3
		rows = (len(instances) + cols - 1) // cols
		fig, axes = plt.subplots(rows, cols, figsize=(5 * cols, 4 * rows), squeeze=False)
		for idx, inst in enumerate(instances):
			r = idx // cols
			c = idx % cols
			panel = df[df["instance_id"].astype(str) == str(inst)]
			if panel.empty:
				axes[r, c].axis("off")
				continue
			sns.boxplot(data=panel, x="energy_consumption_rate_kWh_per_km", y="total_route_time_hours", ax=axes[r, c], color="#4c78a8")
			axes[r, c].set_title(f"Instance {inst}")
			axes[r, c].set_xlabel("Consumption (kWh/km)")
			axes[r, c].set_ylabel("Time (h)")
		# Hide any extra axes
		for j in range(len(instances), rows * cols):
			r = j // cols
			c = j % cols
			axes[r, c].axis("off")
		out_path = os.path.join(self.OUTPUT_DIR, "per_instance_times.png")
		plt.tight_layout()
		plt.savefig(out_path, dpi=300)
		plt.close()
		return out_path

	# ---------- Paired Greedy vs Labeling ----------
	def save_paired_slope_plot(self) -> Optional[str]:
		merged = self._prepare_paired_data()
		if merged is None or merged.empty:
			return None
		plt.figure(figsize=(8, 6))
		for _, row in merged.iterrows():
			plt.plot([0, 1], [row["greedy_time_hours"], row["labeling_time_hours"]], color="#4c78a8", alpha=0.2)
		plt.scatter([0] * len(merged), merged["greedy_time_hours"], color="#f58518", label="Greedy", alpha=0.6)
		plt.scatter([1] * len(merged), merged["labeling_time_hours"], color="#4c78a8", label="Labeling", alpha=0.6)
		plt.xticks([0, 1], ["Greedy", "Labeling"])
		plt.ylabel("Completion time (hours)")
		plt.title("Paired comparison: Greedy vs Labeling")
		plt.legend()
		out_path = os.path.join(self.OUTPUT_DIR, "paired_slope_greedy_vs_labeling.png")
		plt.tight_layout()
		plt.savefig(out_path, dpi=300)
		plt.close()
		return out_path

	def save_paired_csv(self) -> Optional[str]:
		"""Write a CSV summarizing greedy vs labeling times per scenario.

		Columns:
		- instance_id, charging_station_interval_km, battery_capacity_kWh, charging_power_kW,
		  energy_consumption_rate_kWh_per_km, labeling_time_hours, greedy_time_hours,
		  percent_labeling_better (=(greedy - labeling)/greedy)
		"""
		merged = self._prepare_paired_data()
		if merged is None or merged.empty:
			return None
		out_path = os.path.join(self.OUTPUT_DIR, "paired_greedy_labeling_summary.csv")
		cols = [
			"instance_id",
			"charging_station_interval_km",
			"battery_capacity_kWh",
			"charging_power_kW",
			"energy_consumption_rate_kWh_per_km",
			"labeling_time_hours",
			"greedy_time_hours",
			"percent_improvement",
		]
		# Ensure columns exist
		keep = [c for c in cols if c in merged.columns]
		df = merged[keep].copy()
		# Rename percent_improvement to percent_labeling_better for clarity
		if "percent_improvement" in df.columns:
			df = df.rename(columns={"percent_improvement": "percent_labeling_better"})
		df.to_csv(out_path, index=False)
		return out_path

	def save_improvement_boxplot_per_instance(self) -> Optional[str]:
		"""One boxplot per instance for percent improvement (labeling vs greedy)."""
		merged = self._prepare_paired_data()
		if merged is None or merged.empty or "instance_id" not in merged.columns:
			return None
		df = merged[["instance_id", "percent_improvement"]].dropna().copy()
		if df.empty:
			return None
		# Ensure string x labels and consistent order
		df["instance_id"] = df["instance_id"].astype(str)
		instances = sorted(df["instance_id"].unique(), key=lambda x: (len(x), x))
		plt.figure(figsize=(max(8, 0.6 * len(instances)), 5))
		sns.boxplot(data=df, x="instance_id", y="percent_improvement", color="#4c78a8")
		plt.axhline(0, color="#999", linestyle="--", linewidth=1)
		plt.xlabel("Instance ID")
		plt.ylabel("% improvement (Labeling vs Greedy)")
		plt.title("Percent improvement by instance (boxplot)")
		plt.xticks(rotation=45, ha="right")
		out_path = os.path.join(self.OUTPUT_DIR, "per_instance_improvement_boxplot.png")
		plt.tight_layout()
		plt.savefig(out_path, dpi=300)
		plt.close()
		return out_path

	def _labeling_df(self) -> Optional[pd.DataFrame]:
		"""Return labeling-only dataframe with required fields if present."""
		df = self.df.copy()
		if df is None or df.empty:
			return None
		# Instance id
		if "instance_id" not in df.columns:
			return None
		# Route time
		if "total_route_time_hours" not in df.columns:
			return None
		return df

	def save_labeling_time_boxplot_per_instance(self) -> Optional[str]:
		"""Boxplot per instance for labeling total route time (hours)."""
		df = self._labeling_df()
		if df is None:
			return None
		df = df[df["feasible"] & df["total_route_time_hours"].notna()].copy()
		if df.empty:
			return None
		df["instance_id"] = df["instance_id"].astype(str)
		instances = sorted(df["instance_id"].unique(), key=lambda x: (len(x), x))
		plt.figure(figsize=(max(8, 0.6 * len(instances)), 5))
		sns.boxplot(data=df, x="instance_id", y="total_route_time_hours", color="#72b7b2")
		plt.xlabel("Instance ID")
		plt.ylabel("Labeling total route time (h)")
		plt.title("Labeling completion time by instance")
		plt.xticks(rotation=45, ha="right")
		out_path = os.path.join(self.OUTPUT_DIR, "labeling_time_boxplot_per_instance.png")
		plt.tight_layout()
		plt.savefig(out_path, dpi=300)
		plt.close()
		return out_path

	def save_label_counts_bars_per_instance(self) -> Optional[str]:
		"""Side-by-side bars per instance: average labels generated vs dominated (labeling)."""
		df = self._labeling_df()
		if df is None:
			return None
		# Try to discover column names for labels generated/dominated
		cands_gen = [c for c in df.columns if c.lower() in (
			"labelsgenerated", "labels_generated", "num_labels_generated",
			"number_of_labels_generated"
		)] 
		cands_dom = [c for c in df.columns if c.lower() in (
			"labelsdominated", "labels_dominated", "num_labels_dominated",
			"number_of_labels_dominated"
		)]
		if not cands_gen or not cands_dom:
			return None
		col_gen = cands_gen[0]
		col_dom = cands_dom[0]
		df2 = df[["instance_id", col_gen, col_dom]].copy()
		df2 = df2.rename(columns={col_gen: "labels_generated", col_dom: "labels_dominated"})
		# Aggregate mean per instance
		agg = df2.groupby("instance_id")[['labels_generated', 'labels_dominated']].mean().reset_index()
		melt = agg.melt(id_vars="instance_id", value_vars=["labels_generated", "labels_dominated"], var_name="metric", value_name="count")
		melt["instance_id"] = melt["instance_id"].astype(str)
		instances = sorted(melt["instance_id"].unique(), key=lambda x: (len(x), x))
		plt.figure(figsize=(max(9, 0.7 * len(instances)), 5))
		sns.barplot(data=melt, x="instance_id", y="count", hue="metric", palette=["#4c78a8", "#f58518"])
		plt.xlabel("Instance ID")
		plt.ylabel("Average count")
		plt.title("Labels generated vs dominated (labeling): per instance")
		plt.xticks(rotation=45, ha="right")
		plt.legend(title="Metric")
		out_path = os.path.join(self.OUTPUT_DIR, "label_counts_per_instance.png")
		plt.tight_layout()
		plt.savefig(out_path, dpi=300)
		plt.close()
		return out_path

	def save_labeling_compute_time_boxplot_per_instance(self) -> Optional[str]:
		"""Boxplot per instance for labeling computation time (hours or seconds if provided)."""
		df = self._labeling_df()
		if df is None:
			return None
		# Try to locate a compute time column
		cand_cols = [c for c in df.columns if c.lower() in (
			"totaltime", "total_time", "computation_time", "computation_time_seconds"
		)]
		if not cand_cols:
			return None
		col = cand_cols[0]
		df = df[["instance_id", col]].copy()
		df = df.rename(columns={col: "compute_time"})
		# If compute_time looks like seconds (large), keep as-is; otherwise, assume hours
		df["compute_time"] = pd.to_numeric(df["compute_time"], errors="coerce")
		df = df.dropna(subset=["compute_time"])
		if df.empty:
			return None
		df["instance_id"] = df["instance_id"].astype(str)
		instances = sorted(df["instance_id"].unique(), key=lambda x: (len(x), x))
		plt.figure(figsize=(max(8, 0.6 * len(instances)), 5))
		sns.boxplot(data=df, x="instance_id", y="compute_time", color="#e45756")
		plt.xlabel("Instance ID")
		plt.ylabel("Compute time")
		plt.title("Labeling compute time by instance")
		plt.xticks(rotation=45, ha="right")
		out_path = os.path.join(self.OUTPUT_DIR, "labeling_compute_time_boxplot_per_instance.png")
		plt.tight_layout()
		plt.savefig(out_path, dpi=300)
		plt.close()
		return out_path

	def save_improvement_violin_by_cs(self) -> Optional[str]:
		merged = self._prepare_paired_data()
		if merged is None or merged.empty:
			return None
		plt.figure(figsize=(8, 5))
		sns.violinplot(data=merged, x="charging_station_interval_km", y="percent_improvement", color="#72b7b2", inner="box")
		plt.xlabel("CS interval (km)")
		plt.ylabel("% improvement (Labeling vs Greedy)")
		plt.title("Percent improvement by CS interval")
		out_path = os.path.join(self.OUTPUT_DIR, "improvement_by_cs_interval.png")
		plt.tight_layout()
		plt.savefig(out_path, dpi=300)
		plt.close()
		return out_path

	def save_per_instance_improvement_violin(self, max_instances: int = 12) -> Optional[str]:
		merged = self._prepare_paired_data()
		if merged is None or merged.empty or "instance_id" not in merged.columns:
			return None
		instances = list(pd.Series(merged["instance_id"].dropna().unique()).sort_values())
		instances = instances[:max_instances]
		filt = merged[merged["instance_id"].isin(instances)]
		plt.figure(figsize=(max(8, 0.6 * len(instances)), 5))
		sns.violinplot(data=filt, x="instance_id", y="percent_improvement", color="#4c78a8", inner="box")
		plt.xlabel("Instance ID")
		plt.ylabel("% improvement (Labeling vs Greedy)")
		plt.title("Percent improvement by instance")
		plt.xticks(rotation=45, ha="right")
		out_path = os.path.join(self.OUTPUT_DIR, "per_instance_improvement_violin.png")
		plt.tight_layout()
		plt.savefig(out_path, dpi=300)
		plt.close()
		return out_path

	def save_paired_slope_plots_per_instance(self, max_instances: Optional[int] = None) -> List[str]:
		merged = self._prepare_paired_data()
		if merged is None or merged.empty or "instance_id" not in merged.columns:
			return []
		instances = list(pd.Series(merged["instance_id"].dropna().unique()).sort_values())
		if max_instances is not None:
			instances = instances[:max_instances]
		paths: List[str] = []
		for inst in instances:
			sub = merged[merged["instance_id"].astype(str) == str(inst)]
			if sub.empty:
				continue
			plt.figure(figsize=(7, 5))
			for _, row in sub.iterrows():
				plt.plot([0, 1], [row["greedy_time_hours"], row["labeling_time_hours"]], color="#4c78a8", alpha=0.25)
			plt.scatter([0] * len(sub), sub["greedy_time_hours"], color="#f58518", label="Greedy", alpha=0.7)
			plt.scatter([1] * len(sub), sub["labeling_time_hours"], color="#4c78a8", label="Labeling", alpha=0.7)
			plt.xticks([0, 1], ["Greedy", "Labeling"])
			plt.ylabel("Completion time (hours)")
			plt.title(f"Paired comparison (Instance {inst})")
			plt.legend()
			fname = f"paired_slope_greedy_vs_labeling_inst_{inst}.png"
			out_path = os.path.join(self.OUTPUT_DIR, fname)
			plt.tight_layout()
			plt.savefig(out_path, dpi=300)
			plt.close()
			paths.append(out_path)
		return paths

	# ---------- Statistical Layer ----------
	def _prepare_anova_data(self) -> pd.DataFrame:
		df = self.df[self.df["feasible"] & self.df["total_route_time_hours"].notna()].copy()
		# Log-transform if skewed
		vals = df["total_route_time_hours"].dropna().values
		if len(vals) > 0:
			import scipy.stats as stats
			if np.isfinite(vals).all() and abs(stats.skew(vals)) > 1.0:
				df["rt"] = np.log(vals)
			else:
				df["rt"] = df["total_route_time_hours"].astype(float)
		else:
			df["rt"] = df["total_route_time_hours"].astype(float)
		# Cast categorical
		for col in [
			"battery_capacity_kWh",
			"charging_station_interval_km",
			"charging_power_kW",
			"energy_consumption_rate_kWh_per_km",
			"instance_id",
		]:
			df[col] = df[col].astype(str)
		return df

	def save_mixedlm_summary(self) -> Optional[str]:
		try:
			import statsmodels.formula.api as smf
		except Exception:
			return None
		df = self._prepare_anova_data()
		if df.empty:
			return None
		formula = (
			"rt ~ C(battery_capacity_kWh) + C(charging_station_interval_km) + C(charging_power_kW) + C(energy_consumption_rate_kWh_per_km) "
			"+ C(battery_capacity_kWh):C(charging_station_interval_km) + C(battery_capacity_kWh):C(charging_power_kW) + C(battery_capacity_kWh):C(energy_consumption_rate_kWh_per_km) "
			"+ C(charging_station_interval_km):C(charging_power_kW) + C(charging_station_interval_km):C(energy_consumption_rate_kWh_per_km) + C(charging_power_kW):C(energy_consumption_rate_kWh_per_km)"
		)
		try:
			model = smf.mixedlm(formula, df, groups=df["instance_id"]).fit(reml=True, method="lbfgs")
		except Exception:
			# Fallback to default optimizer
			model = smf.mixedlm(formula, df, groups=df["instance_id"]).fit(reml=True)
		out_path = os.path.join(self.OUTPUT_DIR, "mixedlm_summary.txt")
		with open(out_path, "w") as f:
			f.write(str(model.summary()))
		return out_path

	def _anova_with_instance_fe(self) -> Optional[pd.DataFrame]:
		try:
			import statsmodels.api as sm
			from statsmodels.stats.anova import anova_lm
		except Exception:
			return None
		df = self._prepare_anova_data()
		if df.empty:
			return None
		formula = (
			"rt ~ C(instance_id) + C(battery_capacity_kWh) + C(charging_station_interval_km) + C(charging_power_kW) + C(energy_consumption_rate_kWh_per_km) "
			"+ C(battery_capacity_kWh):C(charging_station_interval_km) + C(battery_capacity_kWh):C(charging_power_kW) + C(battery_capacity_kWh):C(energy_consumption_rate_kWh_per_km) "
			"+ C(charging_station_interval_km):C(charging_power_kW) + C(charging_station_interval_km):C(energy_consumption_rate_kWh_per_km) + C(charging_power_kW):C(energy_consumption_rate_kWh_per_km)"
		)
		ols = sm.formula.ols(formula, data=df).fit()
		anova = anova_lm(ols, typ=2)
		# Partial eta squared
		if "Residual" in anova.index:
			ss_error = anova.loc["Residual", "sum_sq"]
		else:
			ss_error = float("nan")
		eta = []
		for idx, row in anova.iterrows():
			if idx == "Residual":
				continue
			ss = row.get("sum_sq", np.nan)
			eta_p = ss / (ss + ss_error) if np.isfinite(ss) and np.isfinite(ss_error) and (ss + ss_error) > 0 else np.nan
			eta.append({"effect": idx, "df": row.get("df", np.nan), "F": row.get("F", np.nan), "Pr(>F)": row.get("PR(>F)", np.nan), "partial_eta_sq": eta_p})
		return pd.DataFrame(eta)

	def save_anova_effects(self) -> Optional[str]:
		anova_df = self._anova_with_instance_fe()
		if anova_df is None or anova_df.empty:
			return None
		out_path = os.path.join(self.OUTPUT_DIR, "anova_effects.csv")
		anova_df.to_csv(out_path, index=False)
		return out_path

	def save_anova_bootstrap_cis(self, n_boot: int = 200, random_state: int = 42) -> Optional[str]:
		try:
			import statsmodels.api as sm
			from statsmodels.stats.anova import anova_lm
		except Exception:
			return None
		df_full = self._prepare_anova_data()
		if df_full.empty or "instance_id" not in df_full.columns:
			return None
		rng = np.random.default_rng(random_state)
		instances = list(pd.Series(df_full["instance_id"].unique()))
		if not instances:
			return None
		# Build formula once
		formula = (
			"rt ~ C(instance_id) + C(battery_capacity_kWh) + C(charging_station_interval_km) + C(charging_power_kW) + C(energy_consumption_rate_kWh_per_km) "
			"+ C(battery_capacity_kWh):C(charging_station_interval_km) + C(battery_capacity_kWh):C(charging_power_kW) + C(battery_capacity_kWh):C(energy_consumption_rate_kWh_per_km) "
			"+ C(charging_station_interval_km):C(charging_power_kW) + C(charging_station_interval_km):C(energy_consumption_rate_kWh_per_km) + C(charging_power_kW):C(energy_consumption_rate_kWh_per_km)"
		)
		boot_rows: Dict[str, List[float]] = {}
		for b in range(n_boot):
			boot_ids = rng.choice(instances, size=len(instances), replace=True)
			df_boot = pd.concat([df_full[df_full["instance_id"] == inst] for inst in boot_ids], ignore_index=True)
			try:
				ols = sm.formula.ols(formula, data=df_boot).fit()
				anova = anova_lm(ols, typ=2)
				ss_error = anova.loc["Residual", "sum_sq"] if "Residual" in anova.index else np.nan
				for idx, row in anova.iterrows():
					if idx == "Residual":
						continue
					ss = row.get("sum_sq", np.nan)
					eta_p = ss / (ss + ss_error) if np.isfinite(ss) and np.isfinite(ss_error) and (ss + ss_error) > 0 else np.nan
					boot_rows.setdefault(idx, []).append(eta_p)
			except Exception:
				continue
		# Aggregate CIs
		out_records = []
		for effect, vals in boot_rows.items():
			vals = [v for v in vals if np.isfinite(v)]
			if not vals:
				continue
			lo, hi = np.quantile(vals, [0.025, 0.975])
			out_records.append({"effect": effect, "partial_eta_sq_ci_lo": lo, "partial_eta_sq_ci_hi": hi, "n_boot": len(vals)})
		if not out_records:
			return None
		out_path = os.path.join(self.OUTPUT_DIR, "anova_effects_bootstrap_ci.csv")
		pd.DataFrame(out_records).to_csv(out_path, index=False)
		return out_path

	@staticmethod
	def _cliffs_delta(a: np.ndarray, b: np.ndarray) -> float:
		# Efficient calculation using sorting
		a = np.asarray(a)
		b = np.asarray(b)
		a = a[np.isfinite(a)]
		b = b[np.isfinite(b)]
		if len(a) == 0 or len(b) == 0:
			return np.nan
		a_sorted = np.sort(a)
		b_sorted = np.sort(b)
		i = j = more = less = 0
		na, nb = len(a_sorted), len(b_sorted)
		while i < na and j < nb:
			if a_sorted[i] > b_sorted[j]:
				more += na - i
				j += 1
			elif a_sorted[i] < b_sorted[j]:
				less += nb - j
				i += 1
			else:
				i += 1
				j += 1
		return (more - less) / (na * nb)

	@staticmethod
	def _hodges_lehmann(a: np.ndarray, b: np.ndarray) -> float:
		# Median of all pairwise differences a - b
		a = np.asarray(a)
		b = np.asarray(b)
		a = a[np.isfinite(a)]
		b = b[np.isfinite(b)]
		if len(a) == 0 or len(b) == 0:
			return np.nan
		diffs = a.reshape(-1, 1) - b.reshape(1, -1)
		return np.median(diffs)

	def save_pairwise_effects(self) -> List[Optional[str]]:
		df = self.df[self.df["feasible"] & self.df["total_route_time_hours"].notna()].copy()
		if df.empty:
			return [None, None]
		factors = [
			("battery_capacity_kWh", "Battery"),
			("charging_station_interval_km", "CS_interval"),
			("charging_power_kW", "CP"),
			("energy_consumption_rate_kWh_per_km", "Consumption"),
		]
		agg_rows = []
		inst_rows = []
		for col, fac_name in factors:
			levels = sorted(df[col].dropna().unique())
			for i in range(len(levels)):
				for j in range(i + 1, len(levels)):
					l_i, l_j = levels[i], levels[j]
					ai = df[df[col] == l_i]["total_route_time_hours"].values
					aj = df[df[col] == l_j]["total_route_time_hours"].values
					delta = self._cliffs_delta(ai, aj)
					hl = self._hodges_lehmann(ai, aj)
					agg_rows.append({"factor": fac_name, "level_a": l_i, "level_b": l_j, "cliffs_delta": delta, "hodges_lehmann_shift": hl, "n_a": len(ai), "n_b": len(aj)})
					# Per-instance
					if "instance_id" in df.columns:
						for inst, part in df.groupby("instance_id"):
							ai = part[part[col] == l_i]["total_route_time_hours"].values
							aj = part[part[col] == l_j]["total_route_time_hours"].values
							if len(ai) and len(aj):
								delta = self._cliffs_delta(ai, aj)
								hl = self._hodges_lehmann(ai, aj)
								inst_rows.append({"instance_id": inst, "factor": fac_name, "level_a": l_i, "level_b": l_j, "cliffs_delta": delta, "hodges_lehmann_shift": hl, "n_a": len(ai), "n_b": len(aj)})
		# Write CSVs
		out1 = os.path.join(self.OUTPUT_DIR, "pairwise_effects_aggregated.csv")
		pd.DataFrame(agg_rows).to_csv(out1, index=False)
		out2 = os.path.join(self.OUTPUT_DIR, "pairwise_effects_by_instance.csv")
		pd.DataFrame(inst_rows).to_csv(out2, index=False)
		return [out1, out2]

	def save_sensitivity_summaries(self) -> Optional[str]:
		df = self.df[self.df["feasible"] & self.df["total_route_time_hours"].notna()].copy()
		if df.empty:
			return None
		rows = []
		groupers = {
			"Battery": "battery_capacity_kWh",
			"CS_interval": "charging_station_interval_km",
			"CP": "charging_power_kW",
			"Consumption": "energy_consumption_rate_kWh_per_km",
		}
		# Aggregated medians
		for fac_name, col in groupers.items():
			agg = df.groupby(col)["total_route_time_hours"].median().reset_index().rename(columns={"total_route_time_hours": "median_time"})
			agg["factor"] = fac_name
			rows.append(agg)
		# Per-instance medians
		if "instance_id" in df.columns:
			for fac_name, col in groupers.items():
				agg = df.groupby(["instance_id", col])["total_route_time_hours"].median().reset_index().rename(columns={"total_route_time_hours": "median_time"})
				agg["factor"] = fac_name
				rows.append(agg)
		out = pd.concat(rows, ignore_index=True)
		out_path = os.path.join(self.OUTPUT_DIR, "sensitivity_main_effects_by_instance.csv")
		out.to_csv(out_path, index=False)
		return out_path

	# ---------- Helper: bootstrap CI ----------
	def _bootstrap_ci(self, values: np.ndarray, estimator: str = "median", n_boot: int = 300, ci: float = 95, random_state: int = 42) -> Tuple[float, float, float, int]:
		vals = np.asarray(values)
		vals = vals[np.isfinite(vals)]
		n = len(vals)
		if n == 0:
			return (np.nan, np.nan, np.nan, 0)
		rng = np.random.default_rng(random_state)
		est_func = np.median if estimator == "median" else np.mean
		est = float(est_func(vals))
		if n < 3:
			return (est, est, est, n)
		boot_stats = []
		for _ in range(n_boot):
			sample = rng.choice(vals, size=n, replace=True)
			boot_stats.append(est_func(sample))
		lo, hi = np.nanquantile(boot_stats, [(100 - ci) / 200, 1 - (100 - ci) / 200])
		return (est, float(lo), float(hi), n)

	def save_improvement_violin_by_cs(self) -> Optional[str]:
		merged = self._prepare_paired_data()
		if merged is None or merged.empty:
			return None
		plt.figure(figsize=(8, 5))
		sns.violinplot(data=merged, x="charging_station_interval_km", y="percent_improvement", color="#72b7b2", inner="box")
		# Add zero reference
		plt.axhline(0, color="#999", linestyle="--", linewidth=1)
		# Overlay median with 95% bootstrap CI and N labels
		cats = sorted(merged["charging_station_interval_km"].dropna().unique())
		xs, ys, yerr_low, yerr_high, ns = [], [], [], [], []
		for x in cats:
			vals = merged.loc[merged["charging_station_interval_km"] == x, "percent_improvement"].values
			est, lo, hi, n = self._bootstrap_ci(vals, estimator="median", n_boot=400)
			xs.append(x)
			ys.append(est)
			yerr_low.append(est - lo)
			yerr_high.append(hi - est)
			ns.append(n)
		plt.errorbar(range(len(xs)), ys, yerr=[yerr_low, yerr_high], fmt="o", color="black", capsize=3, label="Median ±95% CI")
		# Add N labels
		ylim = plt.gca().get_ylim()
		for i, n in enumerate(ns):
			plt.text(i, ylim[0] + 0.02 * (ylim[1] - ylim[0]), f"n={n}", ha="center", va="bottom", fontsize=8, color="#333")
		plt.xlabel("CS interval (km)")
		plt.ylabel("% improvement (Labeling vs Greedy)")
		plt.title("Percent improvement by CS interval")
		plt.legend()
		out_path = os.path.join(self.OUTPUT_DIR, "improvement_by_cs_interval.png")
		plt.tight_layout()
		plt.savefig(out_path, dpi=300)
		plt.close()
		return out_path

	def save_counts_mean_bars(self) -> Optional[str]:
		merged = self._prepare_paired_data()
		if merged is None or merged.empty:
			return None
		# Build mean and CI per metric/approach
		rows = []
		metrics = [
			("Sync events", "greedy_sync_events", "labeling_sync_events"),
			("CS stops", "greedy_cs_stops", "labeling_cs_stops"),
			("Breaks", "greedy_breaks", "labeling_breaks"),
			("Rests", "greedy_rests", "labeling_rests"),
		]
		for label, g_col, l_col in metrics:
			if g_col in merged.columns and l_col in merged.columns:
				for approach, col in [("Greedy", g_col), ("Labeling", l_col)]:
					est, lo, hi, n = self._bootstrap_ci(merged[col].values, estimator="mean", n_boot=400)
					rows.append({"metric": label, "approach": approach, "mean": est, "lo": lo, "hi": hi, "n": n})
		comp = pd.DataFrame(rows)
		if comp.empty:
			return None
		plt.figure(figsize=(9, 5))
		sns.barplot(data=comp, x="metric", y="mean", hue="approach", palette=["#f58518", "#4c78a8"], errorbar=None)
		# Add error bars
		ax = plt.gca()
		# Determine positions
		handles = {}
		for i, (metric, sub) in enumerate(comp.groupby("metric")):
			for j, (approach, row) in enumerate(sub.set_index("approach").iterrows()):
				x = i + (-0.2 if j == 0 else 0.2)
				y = row["mean"]
				yerr = [[y - row["lo"]], [row["hi"] - y]]
				plt.errorbar([x], [y], yerr=yerr, fmt="none", ecolor="#222", capsize=3)
				plt.text(x, y, f"{y:.2f}", ha="center", va="bottom", fontsize=8)
		plt.xlabel("")
		plt.ylabel("Mean count (±95% CI)")
		plt.title("Mean counts: Labeling vs Greedy")
		out_path = os.path.join(self.OUTPUT_DIR, "counts_mean_bars.png")
		plt.tight_layout()
		plt.savefig(out_path, dpi=300)
		plt.close()
		return out_path

	def save_counts_delta_by_consumption(self) -> Optional[str]:
		merged = self._prepare_paired_data()
		if merged is None or merged.empty or "energy_consumption_rate_kWh_per_km" not in merged.columns:
			return None
		melt = []
		for col in ["delta_sync_events", "delta_cs_stops", "delta_breaks", "delta_rests"]:
			if col in merged.columns:
				m = merged[["energy_consumption_rate_kWh_per_km", col]].copy()
				m = m.rename(columns={col: "delta"})
				m["metric"] = col.replace("delta_", "")
				melt.append(m)
		if not melt:
			return None
		melt_df = pd.concat(melt, ignore_index=True)
		plt.figure(figsize=(10, 5))
		sns.violinplot(data=melt_df, x="energy_consumption_rate_kWh_per_km", y="delta", hue="metric", split=True)
		# Zero reference
		plt.axhline(0, color="#999", linestyle="--", linewidth=1)
		# Overlay medians with 95% CI per metric per consumption
		cats = sorted(melt_df["energy_consumption_rate_kWh_per_km"].dropna().unique())
		metrics = sorted(melt_df["metric"].unique())
		offsets = np.linspace(-0.2, 0.2, num=len(metrics))
		for m_idx, met in enumerate(metrics):
			for x_idx, x in enumerate(cats):
				vals = melt_df[(melt_df["metric"] == met) & (melt_df["energy_consumption_rate_kWh_per_km"] == x)]["delta"].values
				est, lo, hi, n = self._bootstrap_ci(vals, estimator="median", n_boot=300)
				plt.errorbar([x_idx + offsets[m_idx]], [est], yerr=[[est - lo], [hi - est]], fmt="o", color="black", capsize=3)
		plt.xlabel("Consumption (kWh/km)")
		plt.ylabel("Delta (Labeling - Greedy)")
		plt.title("Count deltas by consumption (median ±95% CI)")
		out_path = os.path.join(self.OUTPUT_DIR, "counts_delta_by_consumption.png")
		plt.tight_layout()
		plt.savefig(out_path, dpi=300)
		plt.close()
		return out_path

	def save_improvement_by_cs_interval_per_instance(self, max_instances: Optional[int] = 12) -> List[str]:
		merged = self._prepare_paired_data()
		if merged is None or merged.empty or "instance_id" not in merged.columns:
			return []
		instances = list(pd.Series(merged["instance_id"].dropna().unique()).sort_values())
		if max_instances is not None:
			instances = instances[:max_instances]
		paths: List[str] = []
		for inst in instances:
			sub = merged[merged["instance_id"].astype(str) == str(inst)]
			if sub.empty:
				continue
			plt.figure(figsize=(8, 5))
			sns.violinplot(data=sub, x="charging_station_interval_km", y="percent_improvement", color="#72b7b2", inner="box")
			plt.axhline(0, color="#999", linestyle="--", linewidth=1)
			cats = sorted(sub["charging_station_interval_km"].dropna().unique())
			ys = []
			yerr_l = []
			yerr_h = []
			for x in cats:
				vals = sub.loc[sub["charging_station_interval_km"] == x, "percent_improvement"].values
				est, lo, hi, n = self._bootstrap_ci(vals, estimator="median", n_boot=300)
				ys.append(est)
				yerr_l.append(est - lo)
				yerr_h.append(hi - est)
			plt.errorbar(range(len(cats)), ys, yerr=[yerr_l, yerr_h], fmt="o", color="black", capsize=3, label="Median ±95% CI")
			plt.xlabel("CS interval (km)")
			plt.ylabel("% improvement (Labeling vs Greedy)")
			plt.title(f"Percent improvement by CS interval (Instance {inst})")
			plt.legend()
			fname = f"improvement_by_cs_interval_inst_{inst}.png"
			out_path = os.path.join(self.OUTPUT_DIR, fname)
			plt.tight_layout()
			plt.savefig(out_path, dpi=300)
			plt.close()
			paths.append(out_path)
		return paths

	def save_counts_mean_bars_per_instance(self, max_instances: Optional[int] = 12) -> List[str]:
		merged = self._prepare_paired_data()
		if merged is None or merged.empty or "instance_id" not in merged.columns:
			return []
		instances = list(pd.Series(merged["instance_id"].dropna().unique()).sort_values())
		if max_instances is not None:
			instances = instances[:max_instances]
		paths: List[str] = []
		metrics = [
			("Sync events", "greedy_sync_events", "labeling_sync_events"),
			("CS stops", "greedy_cs_stops", "labeling_cs_stops"),
			("Breaks", "greedy_breaks", "labeling_breaks"),
			("Rests", "greedy_rests", "labeling_rests"),
		]
		for inst in instances:
			sub = merged[merged["instance_id"].astype(str) == str(inst)]
			if sub.empty:
				continue
			rows = []
			for label, g_col, l_col in metrics:
				if g_col in sub.columns and l_col in sub.columns:
					for approach, col in [("Greedy", g_col), ("Labeling", l_col)]:
						est, lo, hi, n = self._bootstrap_ci(sub[col].values, estimator="mean", n_boot=300)
						rows.append({"metric": label, "approach": approach, "mean": est, "lo": lo, "hi": hi, "n": n})
			comp = pd.DataFrame(rows)
			if comp.empty:
				continue
			plt.figure(figsize=(9, 5))
			sns.barplot(data=comp, x="metric", y="mean", hue="approach", palette=["#f58518", "#4c78a8"], errorbar=None)
			# Error bars and labels
			for i, (metric, subg) in enumerate(comp.groupby("metric")):
				for j, (approach, row) in enumerate(subg.set_index("approach").iterrows()):
					x = i + (-0.2 if j == 0 else 0.2)
					y = row["mean"]
					yerr = [[y - row["lo"]], [row["hi"] - y]]
					plt.errorbar([x], [y], yerr=yerr, fmt="none", ecolor="#222", capsize=3)
					plt.text(x, y, f"{y:.2f}", ha="center", va="bottom", fontsize=8)
			plt.xlabel("")
			plt.ylabel("Mean count (±95% CI)")
			plt.title(f"Mean counts: Labeling vs Greedy (Instance {inst})")
			fname = f"counts_mean_bars_inst_{inst}.png"
			out_path = os.path.join(self.OUTPUT_DIR, fname)
			plt.tight_layout()
			plt.savefig(out_path, dpi=300)
			plt.close()
			paths.append(out_path)
		return paths

	def save_counts_delta_by_consumption_per_instance(self, max_instances: Optional[int] = 12) -> List[str]:
		merged = self._prepare_paired_data()
		if merged is None or merged.empty or "instance_id" not in merged.columns or "energy_consumption_rate_kWh_per_km" not in merged.columns:
			return []
		instances = list(pd.Series(merged["instance_id"].dropna().unique()).sort_values())
		if max_instances is not None:
			instances = instances[:max_instances]
		paths: List[str] = []
		for inst in instances:
			sub = merged[merged["instance_id"].astype(str) == str(inst)]
			if sub.empty:
				continue
			melt = []
			for col in ["delta_sync_events", "delta_cs_stops", "delta_breaks", "delta_rests"]:
				if col in sub.columns:
					m = sub[["energy_consumption_rate_kWh_per_km", col]].copy()
					m = m.rename(columns={col: "delta"})
					m["metric"] = col.replace("delta_", "")
					melt.append(m)
			if not melt:
				continue
			melt_df = pd.concat(melt, ignore_index=True)
			plt.figure(figsize=(10, 5))
			sns.violinplot(data=melt_df, x="energy_consumption_rate_kWh_per_km", y="delta", hue="metric", split=True)
			plt.axhline(0, color="#999", linestyle="--", linewidth=1)
			cats = sorted(melt_df["energy_consumption_rate_kWh_per_km"].dropna().unique())
			metrics = sorted(melt_df["metric"].unique())
			offsets = np.linspace(-0.2, 0.2, num=len(metrics))
			for m_idx, met in enumerate(metrics):
				for x_idx, x in enumerate(cats):
					vals = melt_df[(melt_df["metric"] == met) & (melt_df["energy_consumption_rate_kWh_per_km"] == x)]["delta"].values
					est, lo, hi, n = self._bootstrap_ci(vals, estimator="median", n_boot=300)
					plt.errorbar([x_idx + offsets[m_idx]], [est], yerr=[[est - lo], [hi - est]], fmt="o", color="black", capsize=3)
			plt.xlabel("Consumption (kWh/km)")
			plt.ylabel("Delta (Labeling - Greedy)")
			plt.title(f"Count deltas by consumption (Instance {inst})")
			fname = f"counts_delta_by_consumption_inst_{inst}.png"
			out_path = os.path.join(self.OUTPUT_DIR, fname)
			plt.tight_layout()
			plt.savefig(out_path, dpi=300)
			plt.close()
			paths.append(out_path)
		return paths

	# ---------- Orchestration ----------
	def generate_all(self) -> List[Optional[str]]:
		outputs: List[Optional[str]] = []
		outputs.append(self.save_feasibility_heatmaps())
		outputs.append(self.save_per_instance_feasibility_grid())
		outputs.append(self.save_feasibility_frontiers())
		outputs.extend(self.save_time_boxplots_by_factor())
		outputs.append(self.save_interaction_battery_cs())
		outputs.append(self.save_interaction_cp_battery())
		outputs.append(self.save_per_instance_small_multiples())
		# Greedy vs labeling comparisons
		outputs.append(self.save_paired_slope_plot())
		outputs.append(self.save_paired_csv())
		outputs.append(self.save_improvement_violin_by_cs())
		outputs.append(self.save_improvement_boxplot_per_instance())
		outputs.append(self.save_labeling_time_boxplot_per_instance())
		outputs.append(self.save_label_counts_bars_per_instance())
		outputs.append(self.save_labeling_compute_time_boxplot_per_instance())
		outputs.append(self.save_sync_delta_vs_time_improvement())
		outputs.append(self.save_counts_mean_bars())
		outputs.append(self.save_counts_delta_by_consumption())
		outputs.append(self.save_per_instance_improvement_violin())
		# Per-instance variants
		outputs.extend(self.save_paired_slope_plots_per_instance(max_instances=12))
		outputs.extend(self.save_counts_mean_bars_per_instance(max_instances=12))
		outputs.extend(self.save_counts_delta_by_consumption_per_instance(max_instances=12))
		outputs.extend(self.save_improvement_by_cs_interval_per_instance(max_instances=12))
		outputs.extend(self.save_interaction_battery_cs_per_instance(max_instances=12))
		outputs.extend(self.save_interaction_cp_battery_per_instance(max_instances=12))
		# Statistical layer
		outputs.append(self.save_mixedlm_summary())
		outputs.append(self.save_anova_effects())
		outputs.append(self.save_anova_bootstrap_cis())
		outputs.extend(self.save_pairwise_effects())
		outputs.append(self.save_sensitivity_summaries())
		return outputs

	def save_counts_mean_bars_per_instance(self, max_instances: Optional[int] = 12) -> List[str]:
		merged = self._prepare_paired_data()
		if merged is None or merged.empty or "instance_id" not in merged.columns:
			return []
		instances = list(pd.Series(merged["instance_id"].dropna().unique()).sort_values())
		if max_instances is not None:
			instances = instances[:max_instances]
		paths: List[str] = []
		metrics = [
			("Sync events", "greedy_sync_events", "labeling_sync_events"),
			("CS stops", "greedy_cs_stops", "labeling_cs_stops"),
			("Breaks", "greedy_breaks", "labeling_breaks"),
			("Rests", "greedy_rests", "labeling_rests"),
		]
		for inst in instances:
			sub = merged[merged["instance_id"].astype(str) == str(inst)]
			if sub.empty:
				continue
			rows = []
			for label, g_col, l_col in metrics:
				if g_col in sub.columns and l_col in sub.columns:
					for approach, col in [("Greedy", g_col), ("Labeling", l_col)]:
						est, lo, hi, n = self._bootstrap_ci(sub[col].values, estimator="mean", n_boot=300)
						rows.append({"metric": label, "approach": approach, "mean": est, "lo": lo, "hi": hi, "n": n})
			comp = pd.DataFrame(rows)
			if comp.empty:
				continue
			plt.figure(figsize=(9, 5))
			sns.barplot(data=comp, x="metric", y="mean", hue="approach", palette=["#f58518", "#4c78a8"], errorbar=None)
			# Error bars and labels
			for i, (metric, subg) in enumerate(comp.groupby("metric")):
				for j, (approach, row) in enumerate(subg.set_index("approach").iterrows()):
					x = i + (-0.2 if j == 0 else 0.2)
					y = row["mean"]
					yerr = [[y - row["lo"]], [row["hi"] - y]]
					plt.errorbar([x], [y], yerr=yerr, fmt="none", ecolor="#222", capsize=3)
					plt.text(x, y, f"{y:.2f}", ha="center", va="bottom", fontsize=8)
			plt.xlabel("")
			plt.ylabel("Mean count (±95% CI)")
			plt.title(f"Mean counts: Labeling vs Greedy (Instance {inst})")
			fname = f"counts_mean_bars_inst_{inst}.png"
			out_path = os.path.join(self.OUTPUT_DIR, fname)
			plt.tight_layout()
			plt.savefig(out_path, dpi=300)
			plt.close()
			paths.append(out_path)
		return paths

	def save_counts_delta_by_consumption_per_instance(self, max_instances: Optional[int] = 12) -> List[str]:
		merged = self._prepare_paired_data()
		if merged is None or merged.empty or "instance_id" not in merged.columns or "energy_consumption_rate_kWh_per_km" not in merged.columns:
			return []
		instances = list(pd.Series(merged["instance_id"].dropna().unique()).sort_values())
		if max_instances is not None:
			instances = instances[:max_instances]
		paths: List[str] = []
		for inst in instances:
			sub = merged[merged["instance_id"].astype(str) == str(inst)]
			if sub.empty:
				continue
			melt = []
			for col in ["delta_sync_events", "delta_cs_stops", "delta_breaks", "delta_rests"]:
				if col in sub.columns:
					m = sub[["energy_consumption_rate_kWh_per_km", col]].copy()
					m = m.rename(columns={col: "delta"})
					m["metric"] = col.replace("delta_", "")
					melt.append(m)
			if not melt:
				continue
			melt_df = pd.concat(melt, ignore_index=True)
			plt.figure(figsize=(10, 5))
			sns.violinplot(data=melt_df, x="energy_consumption_rate_kWh_per_km", y="delta", hue="metric", split=True)
			plt.axhline(0, color="#999", linestyle="--", linewidth=1)
			cats = sorted(melt_df["energy_consumption_rate_kWh_per_km"].dropna().unique())
			metrics = sorted(melt_df["metric"].unique())
			offsets = np.linspace(-0.2, 0.2, num=len(metrics))
			for m_idx, met in enumerate(metrics):
				for x_idx, x in enumerate(cats):
					vals = melt_df[(melt_df["metric"] == met) & (melt_df["energy_consumption_rate_kWh_per_km"] == x)]["delta"].values
					est, lo, hi, n = self._bootstrap_ci(vals, estimator="median", n_boot=300)
					plt.errorbar([x_idx + offsets[m_idx]], [est], yerr=[[est - lo], [hi - est]], fmt="o", color="black", capsize=3)
			plt.xlabel("Consumption (kWh/km)")
			plt.ylabel("Delta (Labeling - Greedy)")
			plt.title(f"Count deltas by consumption (Instance {inst})")
			fname = f"counts_delta_by_consumption_inst_{inst}.png"
			out_path = os.path.join(self.OUTPUT_DIR, fname)
			plt.tight_layout()
			plt.savefig(out_path, dpi=300)
			plt.close()
			paths.append(out_path)
		return paths

	def save_interaction_battery_cs_per_instance(self, max_instances: Optional[int] = 12) -> List[str]:
		df = self.df[self.df["feasible"] & self.df["total_route_time_hours"].notna()].copy()
		if df.empty or "instance_id" not in df.columns:
			return []
		instances = list(pd.Series(df["instance_id"].dropna().unique()).sort_values())
		if max_instances is not None:
			instances = instances[:max_instances]
		paths: List[str] = []
		for inst in instances:
			panel_all = df[df["instance_id"].astype(str) == str(inst)]
			if panel_all.empty:
				continue
			consumptions = sorted(panel_all["energy_consumption_rate_kWh_per_km"].dropna().unique())
			cps = sorted(panel_all["charging_power_kW"].dropna().unique())
			if not consumptions or not cps:
				continue
			fig, axes = plt.subplots(len(consumptions), len(cps), figsize=(5 * len(cps), 4 * len(consumptions)), squeeze=False)
			for r, cons in enumerate(consumptions):
				for c, cp in enumerate(cps):
					panel = panel_all[(panel_all["energy_consumption_rate_kWh_per_km"] == cons) & (panel_all["charging_power_kW"] == cp)]
					if panel.empty:
						axes[r, c].axis("off")
						continue
					agg = panel.groupby(["charging_station_interval_km", "battery_capacity_kWh"])['total_route_time_hours'].median().reset_index()
					for batt, sub in agg.groupby("battery_capacity_kWh"):
						sub = sub.sort_values("charging_station_interval_km")
						axes[r, c].plot(sub["charging_station_interval_km"], sub["total_route_time_hours"], marker="o", label=f"Batt={int(batt)}")
					axes[r, c].set_title(f"Cons={cons}, CP={int(cp)}")
					axes[r, c].set_xlabel("CS interval (km)")
					axes[r, c].set_ylabel("Median time (h)")
					axes[r, c].legend(fontsize=8)
			fname = f"interaction_battery_cs_inst_{inst}.png"
			out_path = os.path.join(self.OUTPUT_DIR, fname)
			plt.tight_layout()
			plt.savefig(out_path, dpi=300)
			plt.close()
			paths.append(out_path)
		return paths

	def save_interaction_cp_battery_per_instance(self, max_instances: Optional[int] = 12) -> List[str]:
		df = self.df[self.df["feasible"] & self.df["total_route_time_hours"].notna()].copy()
		if df.empty or "instance_id" not in df.columns:
			return []
		instances = list(pd.Series(df["instance_id"].dropna().unique()).sort_values())
		if max_instances is not None:
			instances = instances[:max_instances]
		paths: List[str] = []
		for inst in instances:
			panel_all = df[df["instance_id"].astype(str) == str(inst)]
			if panel_all.empty:
				continue
			consumptions = sorted(panel_all["energy_consumption_rate_kWh_per_km"].dropna().unique())
			if not consumptions:
				continue
			fig, axes = plt.subplots(len(consumptions), 1, figsize=(7, 4 * len(consumptions)), squeeze=False)
			for r, cons in enumerate(consumptions):
				panel = panel_all[panel_all["energy_consumption_rate_kWh_per_km"] == cons]
				agg = panel.groupby(["charging_power_kW", "battery_capacity_kWh"])['total_route_time_hours'].median().reset_index()
				for batt, sub in agg.groupby("battery_capacity_kWh"):
					sub = sub.sort_values("charging_power_kW")
					axes[r, 0].plot(sub["charging_power_kW"], sub["total_route_time_hours"], marker="o", label=f"Batt={int(batt)}")
				axes[r, 0].set_title(f"Median time vs CP | Cons={cons} | Inst={inst}")
				axes[r, 0].set_xlabel("Charging power (kW)")
				axes[r, 0].set_ylabel("Median time (h)")
				axes[r, 0].legend(fontsize=8)
			fname = f"interaction_cp_battery_inst_{inst}.png"
			out_path = os.path.join(self.OUTPUT_DIR, fname)
			plt.tight_layout()
			plt.savefig(out_path, dpi=300)
			plt.close()
			paths.append(out_path)
		return paths


def main() -> None:
	analyzer = PerformanceFeasibilityOverview()
	paths = analyzer.generate_all()
	print("Artifacts generated under Results/Post_Analysis:")
	for p in paths:
		if p:
			print(f"- {p}")
		else:
			print("- (skipped one output due to missing data)")


if __name__ == "__main__":
    main() 
