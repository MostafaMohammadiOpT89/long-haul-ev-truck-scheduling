"""
All Parameters Set: Sensitivity Analysis (Partial vs Full, vs Diesel proxy)
  Partial vs Full: paired (full - partial) / partial * 100 at identical EV settings.
  EV vs Diesel:    paired g = 100 * (T_ev - T_diesel) / T_diesel per scenario;
                   T_diesel is one value per structural route instance (not per EV setting).
Diesel proxy: partial_labeling with very large battery and/or diesel_lb_results_*.csv
Output: 
"""

from analysis.inputs import input_path, ANALYSIS_OUTPUT, record_inputs
import pandas as pd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

from common.metrics import add_charging_sync_columns

BASE_DIR = Path(__file__).parent
ALL_PARAMS_DIR = input_path("sweep_unified").parent
CS_SPACING_EXT_DIR = input_path("spacing").parent
OUT_DIR = ANALYSIS_OUTPUT / "sensitivity"
record_inputs(OUT_DIR)
FIG_DIR = OUT_DIR / "figures"
TBL_DIR = OUT_DIR / "tables"
FIG_DIR.mkdir(parents=True, exist_ok=True)
TBL_DIR.mkdir(parents=True, exist_ok=True)

import matplotlib.pyplot as plt
plt.rcParams.update({
    'figure.dpi': 120,
    'font.family': 'serif',
    'font.serif': ['Times New Roman', 'DejaVu Serif', 'Times'],
    'font.size': 10,
    'axes.labelsize': 10,
    'axes.titlesize': 11,
    'axes.facecolor': '#F5F5F5',
    'figure.facecolor': 'white',
    'axes.edgecolor': 'black',
    'axes.linewidth': 0.8,
    'grid.alpha': 0.4,
    'axes.grid': True,
    'axes.axisbelow': True,
})

# Parameter config (matches experiment)
PARAM_RANGES = {
    'consumption_rate': [1.12, 1.49, 2.08],
    'distance_per_cs': [40, 60, 80, 100],
    'battery_capacity': [750, 1000],
    'charging_power': [350, 500, 1000],
}
PARAM_LABELS = {
    'consumption_rate': 'Consumption rate (kWh/km)',
    'distance_per_cs': 'Distance per CS (km)',
    'battery_capacity': 'Battery capacity (kWh)',
    'charging_power': 'Charging power (kW)',
}
DIESEL_PROXY_BATTERY_KWH_MIN = 1.0e9
SENSITIVITY_PARAMS = ['consumption_rate', 'distance_per_cs', 'battery_capacity', 'charging_power']
LINE_SENSITIVITY_PARAMS = ['consumption_rate', 'battery_capacity', 'charging_power']
# Diesel proxy is tied to structural route instance i only (not EV parameters theta).
DIESEL_INSTANCE_KEY = ['instance_clean']
# Operational base case (matches analyze.py / sensitivity experiment centre point)
BASE_CASE = {
    'consumption_rate': 1.49,
    'distance_per_cs': 60.0,
    'battery_capacity': 750.0,
    'charging_power': 350.0,
}
EV_DIESEL_GAP_LABEL = 'EV penalty vs diesel proxy (%)'
MECHANISM_LATEX_META = {
    'consumption_rate': ('Consumption rate', '(kWh/km)'),
    'distance_per_cs': ('Station spacing', '(km)'),
    'battery_capacity': ('Battery capacity', '(kWh)'),
    'charging_power': ('Charging power', '(kW)'),
}
# Extended CS-spacing sweep (stage 1): base-case EV settings, spacing >= 120 km.
SPACING_EXT_MIN_KM = 120.0
SPACING_FIG_MIN_KM = 60.0
SPACING_FIG_MAX_KM = 300.0


def load_csv(filepath):
    from common.results import read_frame
    df = read_frame(filepath)
    if Path(filepath).suffix in (".jsonl", ".json") and "_runner_algorithm" in df:
        df = df[df["_runner_algorithm"].isin(["partial_labeling", "full_labeling", "greedy"])].copy()
    df = df.loc[:, ~df.columns.duplicated()]
    col_map = {
        'computation_time_seconds': 'computation_time_sec',
        'computation_time': 'computation_time_sec',
        'number_of_labels_generated': 'num_labels_generated',
        'number_of_labels_dominated': 'num_labels_dominated',
    }
    for old, new in col_map.items():
        if old in df.columns and new not in df.columns:
            df = df.rename(columns={old: new})
    # Coalesce alternate param columns (unified CSV often has only *_kWh / interval names)
    if 'energy_consumption_rate_kWh_per_km' in df.columns:
        if 'consumption_rate' in df.columns:
            df['consumption_rate'] = df['consumption_rate'].fillna(df['energy_consumption_rate_kWh_per_km'])
        else:
            df['consumption_rate'] = df['energy_consumption_rate_kWh_per_km']
    if 'charging_station_interval_km' in df.columns:
        if 'distance_per_cs' in df.columns:
            df['distance_per_cs'] = df['distance_per_cs'].fillna(df['charging_station_interval_km'])
        else:
            df['distance_per_cs'] = df['charging_station_interval_km']
    if 'battery_capacity_kWh' in df.columns:
        if 'battery_capacity' in df.columns:
            df['battery_capacity'] = df['battery_capacity'].fillna(df['battery_capacity_kWh'])
        else:
            df['battery_capacity'] = df['battery_capacity_kWh']
    if 'charging_power_kW' in df.columns:
        if 'charging_power' in df.columns:
            df['charging_power'] = df['charging_power'].fillna(df['charging_power_kW'])
        else:
            df['charging_power'] = df['charging_power_kW']
    return df


def _battery_kwh_from_row(row) -> float | None:
    for col in ('battery_capacity', 'battery_capacity_kWh'):
        if col not in row.index:
            continue
        v = row[col]
        if pd.notna(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
    return None


def get_strategy(row):
    algo = str(row.get('_runner_algorithm', '')).lower()
    tag = str(row.get('_runner_tag', '')).lower()
    if tag == 'diesel_lb':
        return 'Diesel' if 'partial' in algo else 'Other'
    if 'full' in algo:
        return 'Full'
    if 'partial' in algo:
        b = _battery_kwh_from_row(row)
        if b is not None and b >= DIESEL_PROXY_BATTERY_KWH_MIN:
            return 'Diesel'
        return 'Partial'
    if 'greedy' in algo:
        return 'Greedy'
    return 'Other'


def _prepare_result_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Common columns: strategy, instance_clean, route_time (+ param cols already coalesced)."""
    if df.empty:
        return df
    out = df.copy()
    out['strategy'] = out.apply(get_strategy, axis=1)
    inst_col = 'instance_id' if 'instance_id' in out.columns else 'test_bed_id'
    out['instance_clean'] = (
        out[inst_col].fillna(out.get('test_bed_id', '')).astype(str).str.replace('TB_', '')
    )
    if 'total_route_time_hours' in out.columns:
        out['route_time'] = out['total_route_time_hours']
        if 'total_time' in out.columns:
            out['route_time'] = out['route_time'].fillna(out['total_time'])
    elif 'total_time' in out.columns:
        out['route_time'] = out['total_time']
    else:
        out['route_time'] = np.nan
    return out


def load_all_params():
    files = [input_path("sweep_unified")]
    if not files:
        return pd.DataFrame()
    df = _prepare_result_frame(load_csv(files[0]))
    if df.empty:
        return df
    # EV rows only (exclude diesel-proxy battery sentinel)
    if 'battery_capacity' in df.columns:
        b = pd.to_numeric(df['battery_capacity'], errors='coerce')
        df = df[b.isna() | (b < DIESEL_PROXY_BATTERY_KWH_MIN)]
    # Charging sync counts from activity_timeline
    if 'activity_timeline' in df.columns:
        df = add_charging_sync_columns(df, 'activity_timeline')
    return df


def load_cs_spacing_extension() -> pd.DataFrame:
    """Load extended full-recharge CS-spacing sweep (typically 120-300 km, base-case other params)."""
    if not CS_SPACING_EXT_DIR.is_dir():
        return pd.DataFrame()
    candidates = [input_path("spacing")]
    if not candidates:
        return pd.DataFrame()
    raw = load_csv(candidates[0])
    if raw.empty:
        return raw
    out = _prepare_result_frame(raw)
    if 'activity_timeline' in out.columns:
        out = add_charging_sync_columns(out, 'activity_timeline')
    out = out[out['strategy'] == 'Full'].copy()
    if 'distance_per_cs' in out.columns:
        out = out[out['distance_per_cs'] >= SPACING_EXT_MIN_KM - 1e-6]
    return out


def integrate_cs_spacing_extension(ev_df: pd.DataFrame, ext_df: pd.DataFrame) -> pd.DataFrame:
    """Append extended spacing Full rows (no overlap with main grid below 120 km)."""
    if ext_df.empty:
        return ev_df
    return pd.concat([ev_df, ext_df], ignore_index=True, sort=False)


SPACING_SWEEP_FIXED_PARAMS = ('consumption_rate', 'battery_capacity', 'charging_power')


def filter_spacing_sweep_base(df: pd.DataFrame) -> pd.DataFrame:
    """Base-case EV settings for CS-spacing analysis (spacing itself is free to vary)."""
    if df.empty:
        return df
    mask = pd.Series(True, index=df.index)
    for param in SPACING_SWEEP_FIXED_PARAMS:
        if param not in df.columns:
            continue
        mask &= np.isclose(
            pd.to_numeric(df[param], errors='coerce'), BASE_CASE[param], rtol=0.0, atol=1e-4
        )
    return df.loc[mask].copy()


def spacing_values_for_figure(ev_df: pd.DataFrame) -> list[float]:
    """Ordered CS spacings in [SPACING_FIG_MIN_KM, SPACING_FIG_MAX_KM] present in ev_df."""
    if 'distance_per_cs' not in ev_df.columns:
        return []
    vals = sorted(
        v for v in ev_df['distance_per_cs'].dropna().unique()
        if SPACING_FIG_MIN_KM - 1e-6 <= float(v) <= SPACING_FIG_MAX_KM + 1e-6
    )
    return [float(v) for v in vals]


def _unified_run_id() -> str | None:
    unified_files = [input_path("sweep_unified")]
    if not unified_files:
        return None
    stem = unified_files[0].stem  # unified_results_20260407_174118
    parts = stem.split('_')
    return '_'.join(parts[-2:]) if len(parts) >= 3 else None


def load_diesel_proxy():
    """
    Diesel proxy rows from unified (huge-battery partial) and/or diesel_lb_results_*.csv.
    Prefers diesel_lb files whose run id matches the unified export; falls back to any diesel_lb.
    """
    parts: list[pd.DataFrame] = []
    run_id = _unified_run_id()
    unified_files = [input_path("sweep_unified")]
    if unified_files:
        raw = load_csv(unified_files[0])
        if 'battery_capacity' in raw.columns:
            b = pd.to_numeric(raw['battery_capacity'], errors='coerce')
            tag = raw.get('_runner_tag', pd.Series('', index=raw.index)).astype(str).str.lower()
            algo = raw.get('_runner_algorithm', pd.Series('', index=raw.index)).astype(str).str.lower()
            mask = (
                (b >= DIESEL_PROXY_BATTERY_KWH_MIN) | (tag == 'diesel_lb')
            ) & algo.str.contains('partial', na=False)
            if mask.any():
                parts.append(raw.loc[mask])
    diesel_files = [input_path("sweep_diesel")]
    if diesel_files and run_id:
        matched = [f for f in diesel_files if run_id in f.name]
        if matched:
            diesel_files = matched
        elif diesel_files:
            print(
                f"Warning: no diesel_lb_results_*{run_id}*.csv; using {diesel_files[0].name} "
                f"(diesel matched by structural route instance; prefer run id {run_id})."
            )
    for dpath in diesel_files:
        raw = load_csv(dpath)
        algo = raw.get('_runner_algorithm', pd.Series('', index=raw.index)).astype(str).str.lower()
        raw = raw.loc[algo.str.contains('partial', na=False)]
        if not raw.empty:
            parts.append(raw)
    if not parts:
        return pd.DataFrame()
    diesel = _prepare_result_frame(pd.concat(parts, ignore_index=True, sort=False))
    diesel = diesel[diesel['strategy'] == 'Diesel']
    if diesel.empty or 'instance_clean' not in diesel.columns:
        return diesel
    # One diesel-proxy duration per structural route instance (independent of EV settings).
    n_before = len(diesel)
    diesel = (
        diesel.groupby('instance_clean', as_index=False)
        .agg(route_time=('route_time', 'median'), feasible=('feasible', 'first'))
    )
    if len(diesel) < n_before:
        print(
            f"Diesel proxy: collapsed {n_before} rows to {len(diesel)} structural route instances "
            "(one T_i^diesel per instance)."
        )
    return diesel


def update_param_ranges_from_data(ev_df: pd.DataFrame) -> None:
    """Sync PARAM_RANGES with values present in the loaded EV export."""
    for param in SENSITIVITY_PARAMS:
        if param not in ev_df.columns:
            continue
        vals = sorted(ev_df[param].dropna().unique())
        if vals:
            PARAM_RANGES[param] = [float(v) for v in vals]


def report_ev_diesel_merge(merged: pd.DataFrame, *, strategy: str) -> None:
    if merged.empty:
        return
    neg = int((merged['gap_pct'] < 0).sum())
    print(
        f"  {strategy} vs diesel: {len(merged)} paired scenarios, "
        f"{merged['instance_clean'].nunique()} structural instances."
    )
    if neg:
        print(
            f"  Warning: {neg} negative EV-diesel gaps (EV faster than diesel proxy) - "
            "check instance pairing / optimization consistency."
        )


def build_strategy_pair(
    left_df: pd.DataFrame,
    right_df: pd.DataFrame,
    merge_cols: list[str],
    *,
    left_name: str,
    right_name: str,
):
    """Inner-merge feasible pairs; improvement_pct = (left - right) / right * 100."""
    merge_cols = [c for c in merge_cols if c in left_df.columns and c in right_df.columns]
    if not merge_cols or left_df.empty or right_df.empty:
        return pd.DataFrame()

    lcol, rcol = f'route_{left_name}', f'route_{right_name}'
    fcol_l, fcol_r = f'feasible_{left_name}', f'feasible_{right_name}'
    # Keep EV-side sensitivity columns (e.g. battery_capacity) not used in diesel merge keys.
    extra_left = [
        c for c in SENSITIVITY_PARAMS
        if c in left_df.columns and c not in merge_cols
    ]
    left = left_df[merge_cols + extra_left + ['route_time', 'feasible']].rename(
        columns={'route_time': lcol, 'feasible': fcol_l}
    )
    right = right_df[merge_cols + ['route_time', 'feasible']].rename(
        columns={'route_time': rcol, 'feasible': fcol_r}
    )
    m = left.merge(right, on=merge_cols, how='inner')
    if fcol_l in m.columns and fcol_r in m.columns:
        m = m[(m[fcol_l] == True) & (m[fcol_r] == True)]
    elif fcol_l in m.columns:
        m = m[m[fcol_l] == True]
    elif fcol_r in m.columns:
        m = m[m[fcol_r] == True]
    m = m[(m[lcol] > 0) & (m[rcol] > 0)]
    m['improvement_pct'] = (m[lcol] - m[rcol]) / m[rcol] * 100
    return m


def build_partial_vs_full(df):
    """Merge Full and Partial on (instance, consumption_rate, distance_per_cs, battery_capacity, charging_power)."""
    merge_cols = ['instance_clean', 'consumption_rate', 'distance_per_cs', 'battery_capacity', 'charging_power']
    return build_strategy_pair(
        df[df['strategy'] == 'Full'],
        df[df['strategy'] == 'Partial'],
        merge_cols,
        left_name='full',
        right_name='partial',
    )


def build_ev_vs_diesel(ev_df: pd.DataFrame, diesel_df: pd.DataFrame, strategy: str) -> pd.DataFrame:
    """
    Pair each EV scenario (instance i, setting theta) with T_i^diesel for the same structural instance.
    gap_pct = 100 * (T_ev - T_diesel) / T_diesel; positive => EV slower than diesel proxy.
    """
    ev = ev_df[ev_df['strategy'] == strategy].copy()
    if ev.empty or diesel_df.empty:
        return pd.DataFrame()
    merge_cols = [c for c in DIESEL_INSTANCE_KEY if c in ev.columns and c in diesel_df.columns]
    if not merge_cols:
        return pd.DataFrame()

    keep_cols = merge_cols + [c for c in SENSITIVITY_PARAMS if c in ev.columns]
    keep_cols += [c for c in CHARGING_COLS if c in ev.columns and c not in keep_cols]
    ev_sub = ev[keep_cols + ['route_time', 'feasible']].rename(
        columns={'route_time': 'route_ev', 'feasible': 'feasible_ev'}
    )
    diesel_sub = diesel_df[merge_cols + ['route_time', 'feasible']].rename(
        columns={'route_time': 'route_diesel', 'feasible': 'feasible_diesel'}
    )
    m = ev_sub.merge(diesel_sub, on=merge_cols, how='inner')
    if 'feasible_ev' in m.columns and 'feasible_diesel' in m.columns:
        m = m[(m['feasible_ev'] == True) & (m['feasible_diesel'] == True)]
    elif 'feasible_ev' in m.columns:
        m = m[m['feasible_ev'] == True]
    m = m[(m['route_ev'] > 0) & (m['route_diesel'] > 0)]
    m['gap_pct'] = (m['route_ev'] - m['route_diesel']) / m['route_diesel'] * 100
    m['gap_min'] = (m['route_ev'] - m['route_diesel']) * 60
    return m


def build_full_vs_diesel(ev_df: pd.DataFrame, diesel_df: pd.DataFrame):
    return build_ev_vs_diesel(ev_df, diesel_df, 'Full')


def build_partial_vs_diesel(ev_df: pd.DataFrame, diesel_df: pd.DataFrame):
    return build_ev_vs_diesel(ev_df, diesel_df, 'Partial')


def sensitivity_by_param(merged, param, *, value_col: str = 'improvement_pct'):
    """Group by param; mean gap/improvement is taken over paired scenarios (not ratio of means)."""
    if param not in merged.columns or merged.empty or value_col not in merged.columns:
        return pd.DataFrame()
    grp = merged.groupby(param)[value_col].agg(['mean', 'std', 'count']).reset_index()
    grp = grp.rename(columns={'mean': 'mean_pct', 'std': 'std_pct', 'count': 'n'})
    if 'gap_min' in merged.columns:
        min_grp = merged.groupby(param)['gap_min'].agg(['mean', 'std']).reset_index()
        min_grp = min_grp.rename(columns={'mean': 'mean_gap_min', 'std': 'std_gap_min'})
        grp = grp.merge(min_grp, on=param, how='left')
    mechanism_cols = [c for c in CHARGING_COLS if c in merged.columns]
    if mechanism_cols:
        mech_grp = merged.groupby(param)[mechanism_cols].mean().reset_index()
        mech_grp = mech_grp.rename(columns={c: f'mean_{c}' for c in mechanism_cols})
        grp = grp.merge(mech_grp, on=param, how='left')
    return grp


def feasibility_by_param(ev_df: pd.DataFrame, param: str, strategy: str) -> pd.DataFrame:
    """Feasibility rate among all tested EV scenarios at each parameter level."""
    sub = ev_df[ev_df['strategy'] == strategy]
    if sub.empty or param not in sub.columns:
        return pd.DataFrame()
    grp = (
        sub.groupby(param)
        .agg(n_tested=('feasible', 'count'), n_feasible=('feasible', lambda s: int((s == True).sum())))
        .reset_index()
    )
    grp['feasibility_pct'] = np.where(grp['n_tested'] > 0, 100.0 * grp['n_feasible'] / grp['n_tested'], np.nan)
    return grp


def _is_base_case_value(param: str, val: float) -> bool:
    base = BASE_CASE.get(param)
    if base is None:
        return False
    try:
        return bool(np.isclose(float(val), float(base), rtol=0.0, atol=1e-4))
    except (TypeError, ValueError):
        return False


def _format_param_tick(val: float) -> str:
    return f'{int(val)}' if val == int(val) else f'{val:.2f}'


def complete_sensitivity_groups(
    merged: pd.DataFrame,
    param: str,
    *,
    value_col: str = 'improvement_pct',
    feasibility: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Full sensitivity x-axis (all PARAM_RANGES values); empty slots when no paired data."""
    grp = sensitivity_by_param(merged, param, value_col=value_col)
    expected = PARAM_RANGES.get(param, sorted(merged[param].dropna().unique()) if not merged.empty else [])
    rows: list[dict] = []
    for val in expected:
        row = {param: val, 'mean_pct': np.nan, 'std_pct': np.nan, 'n': 0, 'n_tested': 0, 'feasibility_pct': np.nan}
        if 'gap_min' in merged.columns:
            row.update({'mean_gap_min': np.nan, 'std_gap_min': np.nan})
        if not grp.empty:
            match = grp[np.isclose(grp[param].astype(float), float(val), rtol=0.0, atol=1e-4)]
            if not match.empty:
                row.update(match.iloc[0].to_dict())
        if feasibility is not None and not feasibility.empty:
            fmatch = feasibility[np.isclose(feasibility[param].astype(float), float(val), rtol=0.0, atol=1e-4)]
            if not fmatch.empty:
                row['n_tested'] = int(fmatch.iloc[0]['n_tested'])
                row['feasibility_pct'] = float(fmatch.iloc[0]['feasibility_pct'])
        rows.append(row)
    return pd.DataFrame(rows)


def _style_sensitivity_axis(ax, grp: pd.DataFrame, param: str) -> None:
    """Bold x tick at the operational base-case parameter value."""
    labels = [_format_param_tick(v) for v in grp[param]]
    tick_labels = ax.set_xticklabels(labels)
    for lbl, val in zip(tick_labels, grp[param]):
        if _is_base_case_value(param, val):
            lbl.set_fontweight('bold')


def _plot_sensitivity_bars_on_ax(ax, grp: pd.DataFrame, param: str, *, label_fontsize: float = 9):
    """Draw sensitivity bars; skip empty groups; highlight base-case bar."""
    plot_rows = grp[grp['n'].fillna(0).astype(int) > 0].copy()
    if plot_rows.empty:
        ax.set_visible(False)
        return
    x_all = np.arange(len(grp))
    val_to_x = {float(v): i for i, v in enumerate(grp[param])}
    x_plot = [val_to_x[float(v)] for v in plot_rows[param]]
    vals = plot_rows['mean_pct'].values
    colors = [PALETTE[i % len(PALETTE)] for i in x_plot]
    bars = ax.bar(x_plot, vals, color=colors, alpha=0.85)
    y_max = float(np.nanmax(vals))
    y_min = float(np.nanmin(vals))
    pad = max(abs(y_max), abs(y_min), 1.0) * 0.25
    if y_min >= 0:
        ax.set_ylim(0, y_max * 1.25 if y_max > 0 else 5)
    else:
        ax.set_ylim(y_min - pad, y_max + pad)
    ref = max(abs(y_max), abs(y_min), 1.0)
    for bar, (_, row) in zip(bars, plot_rows.iterrows()):
        mean_v = row['mean_pct']
        n_v = int(row['n'])
        if _is_base_case_value(param, row[param]):
            bar.set_edgecolor('black')
            bar.set_linewidth(2.0)
        offset = ref * 0.02
        y_text = mean_v + offset if mean_v >= 0 else mean_v - offset
        va = 'bottom' if mean_v >= 0 else 'top'
        fs = label_fontsize - 1 if label_fontsize > 7 else label_fontsize
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            y_text,
            f"{mean_v:.1f}%\n(n={n_v})",
            ha='center',
            va=va,
            fontsize=fs,
        )
    ax.set_xticks(x_all)
    _style_sensitivity_axis(ax, grp, param)
    ax.axhline(0, color='black', linewidth=0.5)


# Palette for different bars (no algorithm names, just distinct colors)
PALETTE = ['#5B8FA3', '#6B4E8E', '#4A7C59', '#C9A227']


def fig_sensitivity_bar(
    grp,
    param,
    fig_dir,
    title_suffix='(feasible in both)',
    *,
    outfile: str | None = None,
    ylabel: str = '% delta (full - partial) / partial',
):
    """Bar chart: mean % improvement by param value, with n labels."""
    if grp.empty or int(grp['n'].fillna(0).sum()) == 0:
        return
    fig, ax = plt.subplots(figsize=(6, 4))
    _plot_sensitivity_bars_on_ax(ax, grp, param, label_fontsize=9)
    ax.set_ylabel(ylabel)
    ax.set_xlabel(PARAM_LABELS.get(param, param))
    ax.set_title(f"Mean % Change in Total Route Time by {PARAM_LABELS.get(param, param)} {title_suffix}")
    plt.tight_layout()
    safe_name = param.replace(' ', '_')
    out = outfile or f'sensitivity_{safe_name}.png'
    plt.savefig(fig_dir / out, dpi=150, bbox_inches='tight')
    plt.close()


def fig_sensitivity_combined(
    grps,
    fig_dir,
    *,
    outfile: str = 'sensitivity_combined.png',
    ylabel: str = '% delta (full - partial) / partial',
):
    """2x2 combined sensitivity figure (same layout as sensitivity_combined.png)."""
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    axes = axes.flatten()
    for i, param in enumerate(SENSITIVITY_PARAMS):
        grp = grps.get(param, pd.DataFrame())
        ax = axes[i]
        if grp.empty or int(grp['n'].fillna(0).sum()) == 0:
            ax.set_visible(False)
            continue
        _plot_sensitivity_bars_on_ax(ax, grp, param, label_fontsize=8)
        ax.set_ylabel(ylabel)
        ax.set_xlabel(PARAM_LABELS.get(param, param))
        ax.set_title(PARAM_LABELS.get(param, param))
    plt.tight_layout()
    plt.savefig(fig_dir / outfile, dpi=150, bbox_inches='tight')
    plt.close()


def run_sensitivity_pipeline(merged: pd.DataFrame, fig_dir, tbl_dir, df_for_tables=None, *, prefix: str, ylabel: str):
    """Build per-param bars, combined 2x2 figure, and summary tables for one comparison."""
    if merged.empty:
        return {}
    grps = {}
    combined_name = f'sensitivity_combined_{prefix}.png' if prefix else 'sensitivity_combined.png'
    for param in SENSITIVITY_PARAMS:
        grp = complete_sensitivity_groups(merged, param)
        if int(grp['n'].fillna(0).sum()) == 0:
            continue
        grps[param] = grp
        safe = param.replace(' ', '_')
        fig_sensitivity_bar(
            grp,
            param,
            fig_dir,
            title_suffix='(feasible in both)',
            outfile=f'sensitivity_{prefix}_{safe}.png' if prefix else f'sensitivity_{safe}.png',
            ylabel=ylabel,
        )
    if grps:
        fig_sensitivity_combined(grps, fig_dir, outfile=combined_name, ylabel=ylabel)
        save_tables(grps, tbl_dir, df_for_tables, prefix=prefix)
    return grps


def _plot_ev_diesel_line_on_ax(
    ax,
    grp: pd.DataFrame,
    param: str,
    *,
    color: str = '#5B8FA3',
    show_feasibility: bool = False,
):
    """Ordered line plot of mean EV-diesel gap; annotate n (and feasibility if provided)."""
    plot_rows = grp[grp['n'].fillna(0).astype(int) > 0].copy()
    if plot_rows.empty:
        ax.set_visible(False)
        return
    x = plot_rows[param].astype(float).values
    y = plot_rows['mean_pct'].astype(float).values
    ax.plot(x, y, color=color, linewidth=2.8, alpha=0.9, zorder=2)
    for _, row in plot_rows.iterrows():
        xv = float(row[param])
        yv = float(row['mean_pct'])
        ms = 13 if _is_base_case_value(param, xv) else 10
        ax.plot(
            [xv], [yv], marker='o', markersize=ms, color=color,
            markeredgecolor='black' if _is_base_case_value(param, xv) else color,
            markeredgewidth=2.0 if _is_base_case_value(param, xv) else 1.0, zorder=5,
        )
        label = f"{yv:.1f}%\n(n={int(row['n'])})"
        if show_feasibility and pd.notna(row.get('feasibility_pct')):
            label += f"\nfeas={row['feasibility_pct']:.0f}%"
        ax.annotate(
            label,
            (xv, yv),
            textcoords='offset points',
            xytext=(0, 8),
            ha='center',
            fontsize=12,
        )
    y_max = float(np.nanmax(y))
    y_min = float(np.nanmin(y))
    pad = max(abs(y_max), abs(y_min), 1.0) * 0.35
    if y_min >= 0:
        ax.set_ylim(0, y_max + pad)
    else:
        ax.set_ylim(y_min - pad, y_max + pad)
    ax.axhline(0, color='black', linestyle='--', linewidth=0.8, alpha=0.7)
    ax.set_xlabel(PARAM_LABELS.get(param, param), fontsize=14)
    ax.set_title(PARAM_LABELS.get(param, param), fontsize=15)
    ax.tick_params(axis='both', labelsize=13)
    ticks = grp[param].astype(float).values
    ax.set_xticks(ticks)
    tick_labels = ax.set_xticklabels([_format_param_tick(v) for v in ticks], fontsize=13)
    for lbl, val in zip(tick_labels, ticks):
        if _is_base_case_value(param, val):
            lbl.set_fontweight('bold')


def fig_ev_vs_diesel_by_parameter(grps: dict, fig_dir, *, outfile: str, color: str = '#5B8FA3'):
    """1x3 line plots: consumption, battery, charging power."""
    fig, axes = plt.subplots(1, 3, figsize=(18.5, 6.5))
    for ax, param in zip(axes, LINE_SENSITIVITY_PARAMS):
        grp = grps.get(param, pd.DataFrame())
        if grp.empty or int(grp['n'].fillna(0).sum()) == 0:
            ax.set_visible(False)
            continue
        _plot_ev_diesel_line_on_ax(ax, grp, param, color=color)
        if ax.get_visible():
            ax.set_ylabel(EV_DIESEL_GAP_LABEL, fontsize=14)
    fig.suptitle('Mean paired EVâ€“diesel route-time gap by parameter (feasible EV scenarios)', fontsize=17, y=1.03)
    plt.tight_layout()
    fig.savefig(fig_dir / outfile, dpi=200, bbox_inches='tight')
    plt.close(fig)


def _style_spacing_xaxis(ax, grp: pd.DataFrame) -> None:
    ticks = grp['distance_per_cs'].astype(float).values
    ax.set_xticks(ticks)
    labels = ax.set_xticklabels([_format_param_tick(v) for v in ticks])
    for lbl, val in zip(labels, ticks):
        if _is_base_case_value('distance_per_cs', val):
            lbl.set_fontweight('bold')
    if len(ticks) > 8:
        for lbl in labels:
            lbl.set_rotation(45)
            lbl.set_ha('right')
    ax.set_xlabel(PARAM_LABELS['distance_per_cs'], fontsize=14)
    ax.tick_params(axis='both', labelsize=12)


def fig_ev_vs_diesel_spacing(grps: pd.DataFrame, fig_dir, *, outfile: str, strategy: str, color: str = '#5B8FA3'):
    """Two separate figures: EV-diesel gap and feasibility vs station spacing."""
    if grps.empty:
        return
    n_ticks = len(grps)
    fig_w = max(11.0, min(16.0, 0.8 * n_ticks))
    stem = Path(outfile).stem
    penalty_out = f'{stem}_penalty.png'
    feasibility_out = f'{stem}_feasibility.png'

    plot_rows = grps[grps['n'].fillna(0).astype(int) > 0]

    # --- Penalty figure ---
    if not plot_rows.empty:
        fig_p, ax_gap = plt.subplots(figsize=(fig_w, 6.0))
        x = plot_rows['distance_per_cs'].astype(float).values
        y_gap = plot_rows['mean_pct'].astype(float).values
        ax_gap.plot(x, y_gap, color=color, linewidth=2.4, zorder=2)
        for _, row in plot_rows.iterrows():
            xv = float(row['distance_per_cs'])
            yv = float(row['mean_pct'])
            ms = 12 if _is_base_case_value('distance_per_cs', xv) else 9
            ax_gap.plot(
                [xv], [yv], marker='o', markersize=ms, color=color,
                markeredgecolor='black' if _is_base_case_value('distance_per_cs', xv) else color,
                markeredgewidth=2.2 if _is_base_case_value('distance_per_cs', xv) else 1.1,
            )
            ax_gap.annotate(
                f"{yv:.1f}%",
                (xv, yv), textcoords='offset points', xytext=(0, 10), ha='center', fontsize=12,
            )
        ax_gap.axhline(0, color='black', linestyle='--', linewidth=0.8, alpha=0.7)
        ax_gap.set_ylabel(EV_DIESEL_GAP_LABEL, fontsize=14)
        ax_gap.set_title(f'{strategy} recharge: route-time penalty vs diesel proxy', fontsize=16)
        _style_spacing_xaxis(ax_gap, grps)
        plt.tight_layout()
        fig_p.savefig(fig_dir / penalty_out, dpi=200, bbox_inches='tight')
        plt.close(fig_p)

    # --- Feasibility figure ---
    feas_rows = grps[grps['n_tested'].fillna(0).astype(int) > 0]
    if not feas_rows.empty:
        fig_f, ax_feas = plt.subplots(figsize=(fig_w, 4.5))
        xf = feas_rows['distance_per_cs'].astype(float).values
        yf = feas_rows['feasibility_pct'].astype(float).values
        ax_feas.plot(xf, yf, color='#6B4E8E', linewidth=1.8, marker='s', markersize=6)
        for xv, yv in zip(xf, yf):
            ax_feas.annotate(
                f"{yv:.0f}%", (xv, yv), textcoords='offset points', xytext=(0, 6),
                ha='center', fontsize=8,
            )
        ax_feas.set_ylim(0, 105)
        ax_feas.set_ylabel(f'{strategy} feasibility (%)')
        ax_feas.set_title(f'{strategy} recharge feasibility rate by station spacing')
        _style_spacing_xaxis(ax_feas, grps)
        plt.tight_layout()
        fig_f.savefig(fig_dir / feasibility_out, dpi=150, bbox_inches='tight')
        plt.close(fig_f)


def build_spacing_ev_diesel_groups(
    merged: pd.DataFrame,
    ev_df: pd.DataFrame,
    strategy: str,
    spacing_values: list[float],
) -> pd.DataFrame:
    """Gap + feasibility summary by station spacing (extended range supported)."""
    saved = PARAM_RANGES.get('distance_per_cs')
    PARAM_RANGES['distance_per_cs'] = spacing_values
    feas = feasibility_by_param(ev_df, 'distance_per_cs', strategy)
    grp = complete_sensitivity_groups(merged, 'distance_per_cs', value_col='gap_pct', feasibility=feas)
    if saved is not None:
        PARAM_RANGES['distance_per_cs'] = saved
    return grp


def _format_mechanism_value(param: str, val: float) -> str:
    if param == 'distance_per_cs':
        return str(int(val))
    if param == 'battery_capacity' or param == 'charging_power':
        return str(int(val))
    return f'{val:.2f}'.rstrip('0').rstrip('.')


def export_mechanism_latex(
    mechanism_rows: list[dict],
    out_path: Path,
    *,
    caption: str,
    label: str,
    footnote: str,
) -> None:
    """Manuscript-ready LaTeX table: all sensitivity params incl. station spacing."""
    if not mechanism_rows:
        return
    by_param: dict[str, list[dict]] = {p: [] for p in SENSITIVITY_PARAMS}
    for row in mechanism_rows:
        by_param[row['param']].append(row)

    lines = [
        r'\begin{table}[t]',
        r'\centering',
        rf'\caption{{{caption}}}',
        rf'\label{{{label}}}',
        r'\begin{threeparttable}',
        r'\small',
        r'\setlength{\tabcolsep}{3.5pt}',
        r'\renewcommand{\arraystretch}{1.1}',
        r'\begin{tabular}{',
        r'll',
        r'S[table-format=1.2]',
        r'S[table-format=3.0]',
        r'S[table-format=3.1]',
        r'S[table-format=1.2]',
        r'S[table-format=1.2]',
        r'S[table-format=1.2]',
        r'S[table-format=1.2]',
        r'S[table-format=1.2]',
        r'S[table-format=1.2]',
        r'}',
        r'\toprule',
        r'Parameter & Value & {Gap (\%)} & {Gap (min)} & {Feas. (\%)} & {Charges} & {Sync.} & {Unsync.} & {Break} & {Rest} \\',
        r'\midrule',
    ]
    first_block = True
    for param in SENSITIVITY_PARAMS:
        rows = by_param.get(param) or []
        if not rows:
            continue
        if not first_block:
            lines.append(r'\addlinespace')
        first_block = False
        title, unit = MECHANISM_LATEX_META.get(param, (param, ''))
        for i, r in enumerate(rows):
            val = _format_mechanism_value(param, float(r['Value']))
            gap_pct = r['EV-diesel gap %']
            gap_min = r['EV-diesel gap min']
            feas = r['Feasibility %']
            charges = r.get('Charges', '')
            sync = r.get('Sync.', '')
            unsync = r.get('Unsync.', '')
            brk = r.get('Break', '')
            rest = r.get('Rest', '')
            if i == 0:
                param_cell = title
            elif i == 1 and unit:
                param_cell = unit
            else:
                param_cell = ''
            lines.append(
                f'{param_cell} & {val} & {gap_pct} & {gap_min} & {feas} & '
                f'{charges} & {sync} & {unsync} & {brk} & {rest} \\\\'
            )
    lines.extend([
        r'\bottomrule',
        r'\end{tabular}',
        r'\begin{tablenotes}[flushleft]',
        r'\footnotesize',
        rf'\item {footnote}',
        r'\end{tablenotes}',
        r'\end{threeparttable}',
        r'\end{table}',
    ])
    out_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def save_ev_vs_diesel_tables(grps: dict, tbl_dir, *, prefix: str):
    tag = f'_{prefix}' if prefix else ''
    rows = []
    for param, grp in grps.items():
        if grp.empty:
            continue
        out = grp.copy()
        out.to_csv(tbl_dir / f'table_ev_vs_diesel{tag}_{param}.csv', index=False)
        for _, r in grp.iterrows():
            if int(r.get('n', 0) or 0) == 0:
                continue
            rows.append({
                'Parameter': PARAM_LABELS.get(param, param),
                'Value': r[param],
                'Mean EV-diesel gap %': round(float(r['mean_pct']), 2),
                'Mean EV-diesel gap min': round(float(r['mean_gap_min']), 2) if pd.notna(r.get('mean_gap_min')) else '',
                'Std': round(float(r['std_pct']), 2) if pd.notna(r.get('std_pct')) else '',
                'Std min': round(float(r['std_gap_min']), 2) if pd.notna(r.get('std_gap_min')) else '',
                'N paired feasible': int(r['n']),
                'N tested': int(r.get('n_tested', 0) or 0),
                'Feasibility %': round(float(r['feasibility_pct']), 1) if pd.notna(r.get('feasibility_pct')) else '',
            })
    if rows:
        pd.DataFrame(rows).to_csv(tbl_dir / f'table_ev_vs_diesel{tag}_summary.csv', index=False)

    mechanism_rows = []
    mechanism_cols = [
        ('mean_num_charges', 'Charges'),
        ('mean_num_synchronized', 'Sync.'),
        ('mean_num_unsynchronized', 'Unsync.'),
        ('mean_num_sync_with_break', 'Break'),
        ('mean_num_sync_with_rest', 'Rest'),
    ]
    for param in SENSITIVITY_PARAMS:
        grp = grps.get(param)
        if grp is None or grp.empty:
            continue
        for _, r in grp.iterrows():
            if int(r.get('n', 0) or 0) == 0:
                continue
            row = {
                'param': param,
                'Parameter': PARAM_LABELS.get(param, param),
                'Value': r[param],
                'EV-diesel gap %': round(float(r['mean_pct']), 2),
                'EV-diesel gap min': round(float(r['mean_gap_min']), 2) if pd.notna(r.get('mean_gap_min')) else '',
                'N paired feasible': int(r['n']),
                'N tested': int(r.get('n_tested', 0) or 0),
                'Feasibility %': round(float(r['feasibility_pct']), 1) if pd.notna(r.get('feasibility_pct')) else '',
            }
            for source_col, out_col in mechanism_cols:
                row[out_col] = round(float(r[source_col]), 2) if pd.notna(r.get(source_col)) else ''
            mechanism_rows.append(row)
    if mechanism_rows:
        mech_df = pd.DataFrame(mechanism_rows).drop(columns=['param'])
        mech_df.to_csv(tbl_dir / f'table_ev_vs_diesel{tag}_mechanism.csv', index=False)
        if prefix == 'full_vs_diesel':
            export_mechanism_latex(
                mechanism_rows,
                tbl_dir / f'table_ev_vs_diesel{tag}_mechanism.tex',
                caption='Sensitivity summary for optimized full-recharge schedules relative to the diesel proxy.',
                label='tab:sensitivity_full_diesel',
                footnote=(
                    'Gap (\\% and min) is the mean paired route-time penalty of full-recharge vs.\\ diesel-proxy '
                    'schedules. Feas.\\ reports full-recharge feasibility. Charging columns give mean stop counts; '
                    'Sync.\\ and Unsync.\\ indicate stops overlapping or not with mandatory breaks or rests. '
                    'Station-spacing rows use base-case EV settings (1.49 kWh/km, 750 kWh, 350 kW).'
                ),
            )


def run_ev_vs_diesel_pipeline(
    merged: pd.DataFrame,
    ev_df: pd.DataFrame,
    fig_dir,
    tbl_dir,
    *,
    strategy: str,
    prefix: str,
    color: str,
    spacing_merged: pd.DataFrame | None = None,
    spacing_ev_df: pd.DataFrame | None = None,
    spacing_values: list[float] | None = None,
):
    """EV vs diesel: line plots (3 params) + spacing two-panel + summary tables."""
    if merged.empty:
        return {}
    grps: dict[str, pd.DataFrame] = {}
    for param in SENSITIVITY_PARAMS:
        if param == 'distance_per_cs' and spacing_merged is not None and spacing_ev_df is not None:
            continue
        feas = feasibility_by_param(ev_df, param, strategy)
        grp = complete_sensitivity_groups(
            merged, param, value_col='gap_pct', feasibility=feas
        )
        if int(grp['n'].fillna(0).sum()) == 0 and int(grp['n_tested'].fillna(0).sum()) == 0:
            continue
        grps[param] = grp

    if spacing_merged is not None and spacing_ev_df is not None and spacing_values:
        spacing_grp = build_spacing_ev_diesel_groups(
            spacing_merged, spacing_ev_df, strategy, spacing_values
        )
        if int(spacing_grp['n_tested'].fillna(0).sum()) > 0 or int(spacing_grp['n'].fillna(0).sum()) > 0:
            grps['distance_per_cs'] = spacing_grp

    line_grps = {p: grps[p] for p in LINE_SENSITIVITY_PARAMS if p in grps}
    if line_grps:
        fig_ev_vs_diesel_by_parameter(
            line_grps,
            fig_dir,
            outfile=f'sensitivity_combined_{prefix}.png',
            color=color,
        )
    if 'distance_per_cs' in grps:
        fig_ev_vs_diesel_spacing(
            grps['distance_per_cs'],
            fig_dir,
            outfile=f'ev_vs_diesel_{prefix}_spacing.png',
            strategy=strategy,
            color=color,
        )
        grps['distance_per_cs'].to_csv(
            tbl_dir / f'table_ev_vs_diesel_{prefix}_spacing.csv', index=False
        )
    save_ev_vs_diesel_tables(grps, tbl_dir, prefix=prefix)
    return grps


CHARGING_COLS = ['num_charges', 'num_synchronized', 'num_unsynchronized',
                 'num_sync_with_break', 'num_sync_with_rest',
                 'num_unsynchronized_breaks', 'num_unsynchronized_rests']


def fig_charging_boxplot(df, param, fig_dir):
    """Box plot of charging metrics by param value."""
    if not all(c in df.columns for c in CHARGING_COLS):
        return
    param_vals = sorted(df[param].dropna().unique())
    if len(param_vals) < 2:
        return

    metrics = ['num_charges', 'num_synchronized', 'num_unsynchronized',
               'num_sync_with_break', 'num_sync_with_rest']
    metrics = [m for m in metrics if m in df.columns]
    n_met = len(metrics)
    if n_met == 0:
        return

    fig, axes = plt.subplots(2, 3, figsize=(10, 6))
    axes = axes.flatten()
    for i, m in enumerate(metrics):
        ax = axes[i]
        data = [df[df[param] == v][m].dropna().values for v in param_vals]
        bp = ax.boxplot(data, labels=[str(int(v)) if v == int(v) else f'{v:.2f}' for v in param_vals],
                        patch_artist=True)
        for patch in bp['boxes']:
            patch.set_facecolor('#5B8FA3')
            patch.set_alpha(0.7)
        ax.set_ylabel(m.replace('_', ' ').title())
        ax.set_xlabel(PARAM_LABELS.get(param, param))
        ax.set_title(m.replace('_', ' ').title())
        ax.set_ylim(0, None)
    for j in range(len(metrics), len(axes)):
        axes[j].set_visible(False)
    plt.suptitle(f"Charging Sync Metrics by {PARAM_LABELS.get(param, param)}", fontsize=12, y=1.02)
    plt.tight_layout()
    plt.savefig(fig_dir / f'charging_boxplot_{param}.png', dpi=150, bbox_inches='tight')
    plt.close()


def save_tables(grps, tbl_dir, df=None, *, prefix: str = ''):
    tag = f'_{prefix}' if prefix else ''
    for param, grp in grps.items():
        if grp.empty:
            continue
        out_grp = grp.rename(columns={'mean_pct': 'Mean improvement %', 'std_pct': 'Std', 'n': 'N'})
        out_grp.to_csv(tbl_dir / f'table_sensitivity{tag}_{param}.csv', index=False)
    rows = []
    for param, grp in grps.items():
        if grp.empty:
            continue
        for _, r in grp.iterrows():
            rows.append({
                'Parameter': PARAM_LABELS.get(param, param),
                'Value': r[param],
                'Mean improvement %': round(r['mean_pct'], 2),
                'Std': round(r['std_pct'], 2) if pd.notna(r['std_pct']) else '',
                'N': int(r['n']),
            })
    if rows:
        pd.DataFrame(rows).to_csv(tbl_dir / f'table_sensitivity{tag}_summary.csv', index=False)
    # Charging sync per row
    if df is not None and all(c in df.columns for c in CHARGING_COLS):
        key_cols = ['instance_clean', 'strategy', 'consumption_rate', 'distance_per_cs',
                    'battery_capacity', 'charging_power', 'route_time'] + CHARGING_COLS
        key_cols = [c for c in key_cols if c in df.columns]
        df[key_cols].to_csv(tbl_dir / 'table_charging_sync.csv', index=False)


def write_report(grps, report_path, extra_sections: list[dict] | None = None):
    lines = []
    lines.append("# All Parameters Set: Partial vs Full (Route Time Sensitivity)")
    lines.append("")
    lines.append("Mean % improvement = (full - partial) / partial Ã— 100. Feasible in both.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Combined View (Partial vs Full)")
    lines.append("")
    lines.append("![Sensitivity Combined](figures/sensitivity_combined.png)")
    lines.append("")
    if extra_sections:
        for sec in extra_sections:
            lines.append(f"## {sec['title']}")
            lines.append("")
            lines.append(sec['formula'])
            lines.append("")
            lines.append(f"![{sec['title']}]({sec['figure']})")
            lines.append("")
    lines.append("---")
    lines.append("")
    for param, grp in grps.items():
        if grp.empty:
            continue
        lines.append(f"## {PARAM_LABELS.get(param, param)}")
        lines.append("")
        lines.append(f"![{param}](figures/sensitivity_{param}.png)")
        lines.append("")
        lines.append("| Value | Mean improvement % | Std | N |")
        lines.append("|-------|-------------------|-----|---|")
        for _, r in grp.iterrows():
            std_str = f"{r['std_pct']:.2f}" if pd.notna(r['std_pct']) else "-"
            lines.append(f"| {r[param]} | {r['mean_pct']:.2f} | {std_str} | {int(r['n'])} |")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Charging Synchronization")
    lines.append("")
    lines.append("Per test: num_charges, num_synchronized, num_unsynchronized, num_sync_with_break, num_sync_with_rest. Box plots by parameter.")
    lines.append("")
    lines.append("**Table:** `tables/table_charging_sync.csv`")
    lines.append("**Figures:** `charging_boxplot_*.png`")
    lines.append("")
    lines.append("**Figures:** `figures/`")
    lines.append("**Tables:** `tables/`")
    report_path.write_text("\n".join(lines), encoding='utf-8')


def main():
    print("Loading All parameters set...")
    df_main = load_all_params()
    if df_main.empty:
        print("No data found.")
        return
    update_param_ranges_from_data(df_main)
    spacing_ext = load_cs_spacing_extension()
    df = integrate_cs_spacing_extension(df_main, spacing_ext) if not spacing_ext.empty else df_main
    if not spacing_ext.empty:
        sp_vals = sorted(spacing_ext['distance_per_cs'].dropna().unique())
        print(
            f"CS spacing extension: +{len(spacing_ext)} Full rows from {CS_SPACING_EXT_DIR.name} "
            f"(spacing {sp_vals[0]:.0f}-{sp_vals[-1]:.0f} km, base-case other params)."
        )
    print(f"Rows: {len(df)}, strategies: {df['strategy'].unique().tolist()}")
    print(f"Parameter grid in data: { {k: PARAM_RANGES[k] for k in SENSITIVITY_PARAMS} }")

    merged = build_partial_vs_full(df)
    if merged.empty:
        print("No Full/Partial pairs (feasible in both).")
        return
    n_rows = len(merged)
    n_instances = merged["instance_clean"].nunique()
    print(f"Feasible Full+Partial pairs: {n_rows}")
    print(
        "  Each row = one test (same instance + same 4 experiment parameters) with both "
        "Full and Partial feasible and positive route time."
    )
    print(f"  Unique instances (test beds) represented: {n_instances}")
    print(
        "  In the bar charts, n is how many merged rows fall in that bar (one parameter "
        "fixed, the other three and instance still vary). Bar n values differ because each "
        "chart slices the same rows differently; sum of all bar n values for a chart equals "
        f"the total merged rows ({n_rows})."
    )

    grps = run_sensitivity_pipeline(
        merged,
        FIG_DIR,
        TBL_DIR,
        df,
        prefix='',
        ylabel='% delta (full - partial) / partial',
    )
    for param, grp in grps.items():
        sum_n = int(grp["n"].sum())
        print(
            f"  partial_vs_full {param}: {len(grp)} distinct values; sum of bar n = {sum_n}"
        )

    extra_report_sections: list[dict] = []
    diesel_df = load_diesel_proxy()
    if diesel_df.empty:
        print(
            "No diesel-proxy rows in All parameters set/ (unified huge-battery partial or "
            "diesel_lb_results_*.csv). Skipping Full vs Diesel and Partial vs Diesel figures."
        )
    else:
        print(f"Diesel proxy structural instances: {len(diesel_df)}")
        merged_fd = build_full_vs_diesel(df, diesel_df)
        df_spacing_base = filter_spacing_sweep_base(df)
        df_spacing_base = df_spacing_base[
            (df_spacing_base['distance_per_cs'] >= SPACING_FIG_MIN_KM - 1e-6)
            & (df_spacing_base['distance_per_cs'] <= SPACING_FIG_MAX_KM + 1e-6)
        ]
        spacing_values = spacing_values_for_figure(df_spacing_base)
        merged_fd_spacing = build_full_vs_diesel(df_spacing_base, diesel_df) if spacing_values else pd.DataFrame()
        if merged_fd.empty:
            print("No feasible Full+Diesel pairs (instance-level diesel proxy).")
        else:
            report_ev_diesel_merge(merged_fd, strategy='Full')
            run_ev_vs_diesel_pipeline(
                merged_fd, df, FIG_DIR, TBL_DIR,
                strategy='Full', prefix='full_vs_diesel', color='#5B8FA3',
                spacing_merged=merged_fd_spacing if not merged_fd_spacing.empty else None,
                spacing_ev_df=df_spacing_base if not df_spacing_base.empty else None,
                spacing_values=spacing_values or None,
            )
            if spacing_values:
                print(
                    f"  Full vs diesel spacing figure: {len(spacing_values)} spacings "
                    f"({spacing_values[0]:.0f}-{spacing_values[-1]:.0f} km, base-case EV settings)."
                )
            extra_report_sections.append({
                'title': 'Full recharge vs diesel proxy (by parameter)',
                'formula': (
                    'Paired gap g = 100Ã—(T^fullâˆ’T^diesel)/T^diesel per scenario; '
                    'T^diesel is one value per structural route instance. '
                    'Means are over paired feasible scenarios at each parameter level.'
                ),
                'figure': 'figures/sensitivity_combined_full_vs_diesel.png',
            })
            extra_report_sections.append({
                'title': 'Full recharge vs diesel proxy (station spacing â€” penalty)',
                'formula': 'Mean paired EVâ€“diesel route-time gap by station spacing (base-case EV settings, 60â€“300 km).',
                'figure': 'figures/ev_vs_diesel_full_vs_diesel_spacing_penalty.png',
            })
            extra_report_sections.append({
                'title': 'Full recharge vs diesel proxy (station spacing â€” feasibility)',
                'formula': 'Full-recharge feasibility rate by station spacing (same sweep).',
                'figure': 'figures/ev_vs_diesel_full_vs_diesel_spacing_feasibility.png',
            })

        merged_pd = build_partial_vs_diesel(df, diesel_df)
        df_spacing_partial = filter_spacing_sweep_base(df[df['strategy'] == 'Partial'])
        df_spacing_partial = df_spacing_partial[
            (df_spacing_partial['distance_per_cs'] >= SPACING_FIG_MIN_KM - 1e-6)
            & (df_spacing_partial['distance_per_cs'] <= SPACING_FIG_MAX_KM + 1e-6)
        ]
        spacing_values_partial = spacing_values_for_figure(df_spacing_partial)
        merged_pd_spacing = (
            build_partial_vs_diesel(df_spacing_partial, diesel_df)
            if spacing_values_partial else pd.DataFrame()
        )
        if merged_pd.empty:
            print("No feasible Partial+Diesel pairs (instance-level diesel proxy).")
        else:
            report_ev_diesel_merge(merged_pd, strategy='Partial')
            run_ev_vs_diesel_pipeline(
                merged_pd, df, FIG_DIR, TBL_DIR,
                strategy='Partial', prefix='partial_vs_diesel', color='#E07B4D',
                spacing_merged=merged_pd_spacing if not merged_pd_spacing.empty else None,
                spacing_ev_df=df_spacing_partial if not df_spacing_partial.empty else None,
                spacing_values=spacing_values_partial or None,
            )
            extra_report_sections.append({
                'title': 'Partial recharge vs diesel proxy (by parameter)',
                'formula': 'Same paired instance-level diesel benchmark as full vs diesel.',
                'figure': 'figures/sensitivity_combined_partial_vs_diesel.png',
            })
            extra_report_sections.append({
                'title': 'Partial recharge vs diesel proxy (station spacing â€” penalty)',
                'formula': 'Mean paired EVâ€“diesel route-time gap by station spacing.',
                'figure': 'figures/ev_vs_diesel_partial_vs_diesel_spacing_penalty.png',
            })
            extra_report_sections.append({
                'title': 'Partial recharge vs diesel proxy (station spacing â€” feasibility)',
                'formula': 'Partial-recharge feasibility rate by station spacing.',
                'figure': 'figures/ev_vs_diesel_partial_vs_diesel_spacing_feasibility.png',
            })

    if grps:
        write_report(grps, OUT_DIR / 'report.md', extra_report_sections)

    # Charging sync box plots (skipped if <2 distinct param values or metrics missing)
    if all(c in df.columns for c in CHARGING_COLS):
        for param in ['consumption_rate', 'distance_per_cs', 'battery_capacity', 'charging_power']:
            if param in df.columns:
                fig_charging_boxplot(df, param, FIG_DIR)
        n_charging_figs = sum(
            1 for p in ['consumption_rate', 'distance_per_cs', 'battery_capacity', 'charging_power']
            if p in df.columns and (FIG_DIR / f'charging_boxplot_{p}.png').exists()
        )
        if n_charging_figs:
            print(f"Charging sync box plots saved ({n_charging_figs}).")
        else:
            print("Charging sync: metrics present but no box plots (need â‰¥2 values per parameter).")

    if not grps:
        print("No sensitivity tables/figures produced for Partial vs Full.")

    print(f"Figures: {FIG_DIR}")
    print(f"Tables: {TBL_DIR}")
    print("Done.")


if __name__ == "__main__":
    main()
