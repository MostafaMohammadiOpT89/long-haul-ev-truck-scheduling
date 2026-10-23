import json
import os
from typing import List

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns


def load_results(json_path: str) -> pd.DataFrame:
	with open(json_path, 'r') as f:
		data = json.load(f)
	results = data.get('results', [])
	return pd.DataFrame(results)


def build_key(df: pd.DataFrame, key_cols: List[str]) -> pd.Series:
	return df[key_cols].astype(object).apply(lambda row: tuple(row.values.tolist()), axis=1)


def main():
	# File mapping: 20250916 is the "else 0" case; 20250908 is the "else (reqRT)/CP" case
	root_dir = os.path.dirname(__file__)
	file_else0 = os.path.join(root_dir, 'enhanced_results_20250916_091813.json')
	file_fullcharge = os.path.join(root_dir, 'enhanced_results_20250908_172953.json')

	if not os.path.exists(file_else0):
		raise FileNotFoundError(f'File not found: {file_else0}')
	if not os.path.exists(file_fullcharge):
		raise FileNotFoundError(f'File not found: {file_fullcharge}')

	df_else0 = load_results(file_else0)
	df_full = load_results(file_fullcharge)

	# Define the configuration key used to align scenarios
	key_cols = [
		'instance_id',
		'test_bed_id',
		'battery_capacity_kWh',
		'charging_station_interval_km',
		'charging_power_kW',
		'energy_consumption_rate_kWh_per_km',
		'number_of_customer_locations',
		'synchronization_enabled',
	]

	missing_else0 = [c for c in key_cols if c not in df_else0.columns]
	missing_full = [c for c in key_cols if c not in df_full.columns]
	if missing_else0 or missing_full:
		raise KeyError(f'Missing key columns. else0 missing={missing_else0}, fullcharge missing={missing_full}')

	# Keep only feasible rows if desired; but align first to preserve comparability
	# Add a composite key for merging
	df_else0 = df_else0.copy()
	df_full = df_full.copy()
	df_else0['__key__'] = build_key(df_else0, key_cols)
	df_full['__key__'] = build_key(df_full, key_cols)

	# Inner join to keep scenarios present in both
	left_cols = key_cols + [
		'total_route_time_hours',
		'computation_time_seconds',
		'feasible',
		'reason_if_infeasible',
	]
	right_cols = left_cols.copy()

	left = df_else0[left_cols + ['__key__']].rename(columns={
		'total_route_time_hours': 'time_else0_hours',
		'computation_time_seconds': 'compute_else0_s',
		'feasible': 'feasible_else0',
		'reason_if_infeasible': 'reason_else0',
	})
	right = df_full[right_cols + ['__key__']].rename(columns={
		'total_route_time_hours': 'time_fullcharge_hours',
		'computation_time_seconds': 'compute_fullcharge_s',
		'feasible': 'feasible_fullcharge',
		'reason_if_infeasible': 'reason_fullcharge',
	})

	merged = pd.merge(left, right[['__key__', 'time_fullcharge_hours', 'compute_fullcharge_s', 'feasible_fullcharge', 'reason_fullcharge']], on='__key__', how='inner')

	# Compute differences
	merged['delta_hours'] = merged['time_else0_hours'] - merged['time_fullcharge_hours']
	merged['abs_delta_hours'] = merged['delta_hours'].abs()

	# Save CSV summary
	csv_path = os.path.join(root_dir, 'comparison_20250916_else0_vs_20250908_fullcharge.csv')
	cols_out = key_cols + [
		'time_else0_hours', 'time_fullcharge_hours', 'delta_hours', 'abs_delta_hours',
		'compute_else0_s', 'compute_fullcharge_s', 'feasible_else0', 'feasible_fullcharge',
		'reason_else0', 'reason_fullcharge',
	]
	merged[cols_out].to_csv(csv_path, index=False)
	print(f'Wrote comparison CSV: {csv_path} (rows={len(merged)})')

	# Plot settings
	sns.set(style='whitegrid', context='talk')

	# 1) Scatter: full-charge vs else0
	plt.figure(figsize=(9, 7))
	sns.scatterplot(data=merged, x='time_fullcharge_hours', y='time_else0_hours', hue='test_bed_id', alpha=0.7)
	max_axis = float(pd.concat([merged['time_fullcharge_hours'], merged['time_else0_hours']]).max())
	plt.plot([0, max_axis], [0, max_axis], 'k--', linewidth=1)
	plt.xlabel('Total route time (hours) — full charging time (reqRT/CP)')
	plt.ylabel('Total route time (hours) — else 0 overlap case')
	plt.title('Route Time Comparison: Full Charge vs Else-0 (overlap)')
	plt.tight_layout()
	scatter_path = os.path.join(root_dir, 'plot_scatter_time_full_vs_else0.png')
	plt.savefig(scatter_path, dpi=200)
	plt.close()
	print(f'Saved scatter plot: {scatter_path}')

	# 2) Histogram of deltas
	plt.figure(figsize=(9, 6))
	sns.histplot(merged['delta_hours'], bins=40, kde=True, color='#1f77b4')
	plt.axvline(0, color='k', linestyle='--', linewidth=1)
	plt.xlabel('Delta hours (else0 - fullcharge)')
	plt.title('Distribution of Route Time Differences')
	plt.tight_layout()
	hist_path = os.path.join(root_dir, 'plot_hist_delta_hours.png')
	plt.savefig(hist_path, dpi=200)
	plt.close()
	print(f'Saved histogram: {hist_path}')

	# 3) Bar chart for largest absolute differences by instance_id (limit N for readability)
	# Use a label combining instance and key config tuple
	merged['sid_label'] = merged.apply(
		lambda r: f"sid{r['instance_id']}-BC{r['battery_capacity_kWh']}-CS{r['charging_station_interval_km']}-CP{r['charging_power_kW']}-CR{r['energy_consumption_rate_kWh_per_km']}",
		axis=1,
	)
	N = 30
	topN = merged.nlargest(N, 'abs_delta_hours')
	plt.figure(figsize=(12, 8))
	sns.barplot(data=topN, x='abs_delta_hours', y='sid_label', hue='test_bed_id', dodge=False)
	plt.xlabel('|Delta| hours (else0 - fullcharge)')
	plt.ylabel('Scenario (instance/config)')
	plt.title(f'Top {N} Absolute Differences in Route Time')
	plt.tight_layout()
	bar_path = os.path.join(root_dir, 'plot_top_abs_deltas.png')
	plt.savefig(bar_path, dpi=200)
	plt.close()
	print(f'Saved bar chart: {bar_path}')

	# 4) Per-test-bed bar charts of delta for every overlapping scenario in that TB
	for tb in sorted(merged['test_bed_id'].unique()):
		subset = merged[merged['test_bed_id'] == tb].copy()
		if subset.empty:
			continue
		# Sort by delta for readability
		subset = subset.sort_values('delta_hours', ascending=True)
		plt.figure(figsize=(14, max(6, 0.35 * len(subset))))
		sns.barplot(data=subset, x='delta_hours', y='sid_label', color='#1f77b4')
		plt.axvline(0, color='k', linestyle='--', linewidth=1)
		plt.xlabel('Delta hours (else0 - fullcharge)')
		plt.ylabel('Scenario (instance/config)')
		plt.title(f'Delta of Total Route Time by Scenario — {tb}')
		plt.tight_layout()
		out_path = os.path.join(root_dir, f'plot_delta_by_testbed_{tb}.png')
		plt.savefig(out_path, dpi=200)
		plt.close()
		print(f'Saved per-test-bed delta bar chart: {out_path}')

	print('Done.')


if __name__ == '__main__':
	main()


