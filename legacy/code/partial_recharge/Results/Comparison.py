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
	# File mapping: 20250919_123532 is full recharge strategy; 20250919_114743 is partial recharge strategy
	root_dir = os.path.dirname(__file__)
	file_fullcharge = os.path.join(root_dir, 'enhanced_results_20250924_155706.json')
	file_partialcharge = os.path.join(root_dir, 'enhanced_results_20250924_155639.json')

	if not os.path.exists(file_fullcharge):
		raise FileNotFoundError(f'File not found: {file_fullcharge}')
	if not os.path.exists(file_partialcharge):
		raise FileNotFoundError(f'File not found: {file_partialcharge}')

	df_fullcharge = load_results(file_fullcharge)
	df_partialcharge = load_results(file_partialcharge)

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

	missing_fullcharge = [c for c in key_cols if c not in df_fullcharge.columns]
	missing_partialcharge = [c for c in key_cols if c not in df_partialcharge.columns]
	if missing_fullcharge or missing_partialcharge:
		raise KeyError(f'Missing key columns. fullcharge missing={missing_fullcharge}, partialcharge missing={missing_partialcharge}')

	# Keep only feasible rows if desired; but align first to preserve comparability
	# Add a composite key for merging
	df_fullcharge = df_fullcharge.copy()
	df_partialcharge = df_partialcharge.copy()
	df_fullcharge['__key__'] = build_key(df_fullcharge, key_cols)
	df_partialcharge['__key__'] = build_key(df_partialcharge, key_cols)

	# Inner join to keep scenarios present in both
	left_cols = key_cols + [
		'total_route_time_hours',
		'computation_time_seconds',
		'feasible',
		'reason_if_infeasible',
	]
	right_cols = left_cols.copy()

	left = df_fullcharge[left_cols + ['__key__']].rename(columns={
		'total_route_time_hours': 'time_fullcharge_hours',
		'computation_time_seconds': 'compute_fullcharge_s',
		'feasible': 'feasible_fullcharge',
		'reason_if_infeasible': 'reason_fullcharge',
	})
	right = df_partialcharge[right_cols + ['__key__']].rename(columns={
		'total_route_time_hours': 'time_partialcharge_hours',
		'computation_time_seconds': 'compute_partialcharge_s',
		'feasible': 'feasible_partialcharge',
		'reason_if_infeasible': 'reason_partialcharge',
	})

	merged = pd.merge(left, right[['__key__', 'time_partialcharge_hours', 'compute_partialcharge_s', 'feasible_partialcharge', 'reason_partialcharge']], on='__key__', how='inner')

	# Compute differences
	merged['delta_hours'] = merged['time_fullcharge_hours'] - merged['time_partialcharge_hours']
	merged['abs_delta_hours'] = merged['delta_hours'].abs()
	# Percent difference relative to partial (guard divide-by-zero)
	merged['pct_delta'] = (merged['delta_hours'] / merged['time_partialcharge_hours'].replace(0, pd.NA)) * 100
	merged['pct_delta'] = merged['pct_delta'].astype('Float64')

	# Optional: focus on scenarios feasible in both strategies
	merged_both_feasible = merged[(merged['feasible_fullcharge'] == True) & (merged['feasible_partialcharge'] == True)].copy()

	# Save CSV summary
	csv_path = os.path.join(root_dir, 'comparison_20250919_fullcharge_vs_partialcharge.csv')
	cols_out = key_cols + [
		'time_fullcharge_hours', 'time_partialcharge_hours', 'delta_hours', 'abs_delta_hours',
		'compute_fullcharge_s', 'compute_partialcharge_s', 'feasible_fullcharge', 'feasible_partialcharge',
		'reason_fullcharge', 'reason_partialcharge',
	]
	merged[cols_out].to_csv(csv_path, index=False)
	print(f'Wrote comparison CSV: {csv_path} (rows={len(merged)})')

	# Save compact CSV with configuration + totals + diff + percentage
	slim_cols = [
		'instance_id', 'test_bed_id', 'battery_capacity_kWh', 'charging_station_interval_km',
		'charging_power_kW', 'energy_consumption_rate_kWh_per_km', 'number_of_customer_locations',
		'synchronization_enabled', 'time_fullcharge_hours', 'time_partialcharge_hours', 'delta_hours', 'pct_delta'
	]
	csv_path_slim = os.path.join(root_dir, 'comparison_summary_full_vs_partial.csv')
	merged[slim_cols].to_csv(csv_path_slim, index=False)
	print(f'Wrote compact summary CSV: {csv_path_slim} (rows={len(merged)})')

	# Plot settings
	sns.set(style='whitegrid', context='talk')

	# 1) Scatter: full-charge vs partial-charge
	plt.figure(figsize=(9, 7))
	sns.scatterplot(data=merged, x='time_fullcharge_hours', y='time_partialcharge_hours', hue='test_bed_id', alpha=0.7)
	max_axis = float(pd.concat([merged['time_fullcharge_hours'], merged['time_partialcharge_hours']]).max())
	plt.plot([0, max_axis], [0, max_axis], 'k--', linewidth=1)
	plt.xlabel('Total route time (hours) — full charging strategy')
	plt.ylabel('Total route time (hours) — partial charging strategy')
	plt.title('Route Time Comparison: Full Charge vs Partial Charge')
	plt.tight_layout()
	scatter_path = os.path.join(root_dir, 'plot_scatter_time_full_vs_partial.png')
	plt.savefig(scatter_path, dpi=200)
	plt.close()
	print(f'Saved scatter plot: {scatter_path}')

	# 2) Histogram of deltas
	plt.figure(figsize=(9, 6))
	sns.histplot(merged['delta_hours'], bins=40, kde=True, color='#1f77b4')
	plt.axvline(0, color='k', linestyle='--', linewidth=1)
	plt.xlabel('Delta hours (fullcharge - partialcharge)')
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
	plt.xlabel('|Delta| hours (fullcharge - partialcharge)')
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
		plt.xlabel('Delta hours (fullcharge - partialcharge)')
		plt.ylabel('Scenario (instance/config)')
		plt.title(f'Delta of Total Route Time by Scenario — {tb}')
		plt.tight_layout()
		out_path = os.path.join(root_dir, f'plot_delta_by_testbed_{tb}.png')
		plt.savefig(out_path, dpi=200)
		plt.close()
		print(f'Saved per-test-bed delta bar chart: {out_path}')

	# 5) Frequency of cases where full and partial are effectively the same (|delta| <= 0.002 h)
	threshold = 0.002
	merged['is_equal_case'] = merged['abs_delta_hours'] <= threshold
	equal_cases = merged[merged['is_equal_case']].copy()
	print(f"Total equal cases (|delta| <= {threshold} h): {len(equal_cases)} out of {len(merged)}")
	# Overall frequency bar (equal vs not equal)
	plt.figure(figsize=(6, 5))
	ax = sns.countplot(data=merged, x='is_equal_case', color='#1f77b4')
	ax.bar_label(ax.containers[0])
	ax.set_xticklabels(['Not equal', 'Equal'])
	plt.ylabel('Count of scenarios')
	plt.title(f'Frequency of Equal Cases (|delta| <= {threshold} h)')
	plt.tight_layout()
	out_path = os.path.join(root_dir, 'plot_freq_equal_overall.png')
	plt.savefig(out_path, dpi=200)
	plt.close()
	print(f'Saved overall equal frequency: {out_path}')

	# Frequency by test bed for equal cases
	if not equal_cases.empty:
		plt.figure(figsize=(8, 5))
		ax = sns.countplot(data=equal_cases, x='test_bed_id', color='#1f77b4')
		ax.bar_label(ax.containers[0])
		plt.xlabel('test_bed_id')
		plt.ylabel('Equal-case count')
		plt.title('Equal Cases by Test Bed')
		plt.tight_layout()
		out_path = os.path.join(root_dir, 'plot_freq_equal_by_testbed.png')
		plt.savefig(out_path, dpi=200)
		plt.close()
		print(f'Saved equal frequency by test bed: {out_path}')

	# Frequency by configuration levels for equal cases
	param_map = {
		'energy_consumption_rate_kWh_per_km': 'consumptionRates',
		'charging_station_interval_km': 'distancesPerCS',
		'battery_capacity_kWh': 'batteryCaps',
		'charging_power_kW': 'CPs',
	}
	for col, label_name in param_map.items():
		if col not in equal_cases.columns:
			continue
		plt.figure(figsize=(10, 5))
		ax = sns.countplot(data=equal_cases, x=col, color='#1f77b4')
		ax.bar_label(ax.containers[0])
		plt.xlabel(label_name)
		plt.ylabel('Equal-case count')
		plt.title(f'Equal Cases by {label_name}')
		plt.tight_layout()
		out_path = os.path.join(root_dir, f'plot_freq_equal_by_{label_name}.png')
		plt.savefig(out_path, dpi=200)
		plt.close()
		print(f'Saved equal frequency by {label_name}: {out_path}')

	# 6) Frequency of cases with improvement (partial better than full by > threshold)
	merged['is_improvement_case'] = merged['delta_hours'] > threshold  # delta = full - partial
	improvement_cases = merged[merged['is_improvement_case']].copy()
	print(f"Total improvement cases (delta > {threshold} h): {len(improvement_cases)} out of {len(merged)}")
	# Overall improvement vs others
	plt.figure(figsize=(6, 5))
	ax = sns.countplot(data=merged, x='is_improvement_case', color='#2ca02c')
	ax.bar_label(ax.containers[0])
	ax.set_xticklabels(['No improvement', 'Improvement'])
	plt.ylabel('Count of scenarios')
	plt.title(f'Frequency of Improvement Cases (delta > {threshold} h)')
	plt.tight_layout()
	out_path = os.path.join(root_dir, 'plot_freq_improvement_overall.png')
	plt.savefig(out_path, dpi=200)
	plt.close()
	print(f'Saved overall improvement frequency: {out_path}')

	# Improvement by test bed
	if not improvement_cases.empty:
		plt.figure(figsize=(8, 5))
		ax = sns.countplot(data=improvement_cases, x='test_bed_id', color='#2ca02c')
		ax.bar_label(ax.containers[0])
		plt.xlabel('test_bed_id')
		plt.ylabel('Improvement-case count')
		plt.title('Improvement Cases by Test Bed')
		plt.tight_layout()
		out_path = os.path.join(root_dir, 'plot_freq_improvement_by_testbed.png')
		plt.savefig(out_path, dpi=200)
		plt.close()
		print(f'Saved improvement frequency by test bed: {out_path}')

	# Improvement by configuration levels
	for col, label_name in param_map.items():
		if col not in improvement_cases.columns:
			continue
		plt.figure(figsize=(10, 5))
		ax = sns.countplot(data=improvement_cases, x=col, color='#2ca02c')
		ax.bar_label(ax.containers[0])
		plt.xlabel(label_name)
		plt.ylabel('Improvement-case count')
		plt.title(f'Improvement Cases by {label_name}')
		plt.tight_layout()
		out_path = os.path.join(root_dir, f'plot_freq_improvement_by_{label_name}.png')
		plt.savefig(out_path, dpi=200)
		plt.close()
		print(f'Saved improvement frequency by {label_name}: {out_path}')

	# 5) Percent change by key parameters (mean with 95% CI) — direct insight
	param_map = {
		'energy_consumption_rate_kWh_per_km': 'consumptionRates',
		'charging_station_interval_km': 'distancesPerCS',
		'battery_capacity_kWh': 'batteryCaps',
		'charging_power_kW': 'CPs',
	}
	for col, label_name in param_map.items():
		if col not in merged_both_feasible.columns:
			continue
		plt.figure(figsize=(10, 6))
		ax = sns.barplot(data=merged_both_feasible, x=col, y='pct_delta', errorbar='ci', ci=95, estimator='mean', color='#1f77b4')
		# Add mean% and n labels on bars
		stats_df = merged_both_feasible.groupby(col)['pct_delta'].agg(['mean','count']).reset_index()
		stats_df = stats_df.sort_values(by=col)
		for patch, (_, row) in zip(ax.patches, stats_df.iterrows()):
			height = patch.get_height()
			x = patch.get_x() + patch.get_width() / 2
			ax.text(x, height, f"{row['mean']:.1f}%\n(n={int(row['count'])})", ha='center', va='bottom', fontsize=9)
		plt.axhline(0, color='k', linestyle='--', linewidth=1)
		plt.ylabel('% delta (full - partial) / partial')
		plt.xlabel(label_name)
		plt.title(f'Mean % Change in Total Route Time by {label_name} (feasible in both)')
		plt.tight_layout()
		out_path = os.path.join(root_dir, f'plot_pct_delta_by_{label_name}.png')
		plt.savefig(out_path, dpi=200)
		plt.close()
		print(f'Saved mean % delta bar: {out_path}')

	# 6) Distribution view (boxplots) for percent change by parameter
	for col, label_name in param_map.items():
		if col not in merged_both_feasible.columns:
			continue
		plt.figure(figsize=(10, 6))
		ax = sns.boxplot(data=merged_both_feasible, x=col, y='pct_delta')
		# Add sample size labels below x-axis
		counts = merged_both_feasible.groupby(col)['pct_delta'].size()
		ymin, ymax = ax.get_ylim()
		range_y = ymax - ymin
		new_ymin = ymin - 0.12 * range_y
		ax.set_ylim(new_ymin, ymax)
		for xtick, tick_label in zip(ax.get_xticks(), ax.get_xticklabels()):
			grp = tick_label.get_text()
			n = int(counts.get(grp, 0))
			ax.text(xtick, new_ymin + 0.02 * range_y, f"n={n}", ha='center', va='bottom', fontsize=9)
		plt.axhline(0, color='k', linestyle='--', linewidth=1)
		plt.ylabel('% delta (full - partial) / partial')
		plt.xlabel(label_name)
		plt.title(f'Distribution of % Change by {label_name} (feasible in both)')
		plt.tight_layout()
		out_path = os.path.join(root_dir, f'plot_pct_delta_box_by_{label_name}.png')
		plt.savefig(out_path, dpi=200)
		plt.close()
		print(f'Saved % delta boxplot: {out_path}')

	print('Done.')


if __name__ == '__main__':
	main()


