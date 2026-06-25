"""
Base-Scenario Post-Analysis: EV Routing Strategies
Analyzes only the base scenario. No sensitivity analysis.
Output: analysis_output_baseScenario/figures/, analysis_output_baseScenario/tables/, Post_Analysis_Report_BaseScenario.md

Data structure (unified_results_*.csv):
- _runner_algorithm: greedy | partial_labeling | full_labeling
- _runner_tag: nan | diesel_lb (Diesel LB when tag=diesel_lb)
- instance_id / test_bed_id: instance identifier (TB_ prefix stripped for instance_clean)
- Route time: total_route_time_hours (Full, Partial, Diesel) OR total_time (Greedy)
- computation_time / computation_time_seconds
- number_of_labels_generated, number_of_labels_dominated (Full, Partial only)
- Instance naming: short|med|long_cl*_cu*_Balanced|_Unbalanced| (problem size, balance)
- Diesel proxy: partial_labeling with very large battery (e.g. 1e10 kWh) is labeled Partial_Diesel_LB, not Partial.
  full_labeling with the same huge battery stays labeled Full in raw data but is excluded from EV comparisons
  (only nominal base-scenario rows: 750 kWh, 60 km CS spacing, 350 kW, 1.49 kWh/km for labeling algorithms).
  Legacy: _runner_tag == diesel_lb also maps to Partial_Diesel_LB.
- Optional exclusions: set EXCLUDED_INSTANCE_IDS (instance_clean names) to drop tests from all outputs.
- analyze.py loads `unified_results_*.csv` only (not separate algorithm CSVs). If that unified file
  contains no `_runner_algorithm` rows with "greedy", the latest `greedy_results_*.csv` in the same
  folder is appended automatically (with a console note); prefer a unified export that already
  includes greedy so all strategies share one run id.
- Instance IDs: table_00 maps mnemonic id (from test name, e.g. S_cl2_cu4_U) to instance_clean; figures use that id on the x-axis.
- Per-instance summary: `tables/table_summary_route_times_and_activity.csv` (+ `.md` preview) — route times for
  Full, Partial, Greedy, diesel proxy and activity/sync counts (CS stops, breaks, rests, charges, sync metrics).
- Analyst CSVs (thesis/diagnostic numerics): `table_thesis_full_vs_partial_per_instance.csv`,
  `table_thesis_full_vs_partial_by_route_class.csv`, `table_diagnostic_partial_vs_full_extremes.csv`,
  `table_diagnostic_near_diesel_wide.csv`, `table_thesis_diagnostic_caption.txt`.
"""

import re
import sys
from datetime import datetime

import pandas as pd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

from charging_sync import add_charging_sync_columns

# Paths
BASE_DIR = Path(__file__).parent
BASE_SCENARIO_DIR = BASE_DIR / "base scenario"
OUT_DIR = BASE_DIR / "analysis_output_baseScenario"
FIG_DIR = OUT_DIR / "figures"
TBL_DIR = OUT_DIR / "tables"
FIG_DIR.mkdir(parents=True, exist_ok=True)
TBL_DIR.mkdir(parents=True, exist_ok=True)

import matplotlib.pyplot as plt

# Figure style: serif font, subtle gridlines, light grey background, thin border (academic paper style)
plt.rcParams.update({
    'figure.dpi': 120,
    'font.family': 'serif',
    'font.serif': ['Times New Roman', 'DejaVu Serif', 'Times'],
    'font.size': 10,
    'axes.labelsize': 10,
    'axes.titlesize': 11,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
    'legend.fontsize': 9,
    'axes.facecolor': '#F5F5F5',
    'figure.facecolor': 'white',
    'axes.edgecolor': 'black',
    'axes.linewidth': 0.8,
    'grid.alpha': 0.4,
    'grid.linestyle': '-',
    'grid.linewidth': 0.5,
    'axes.grid': True,
    'axes.axisbelow': True,
})


# Partial runs at or above this battery are treated as unconstrained / diesel-style lower bound (same as 1e10 kWh proxy).
DIESEL_PROXY_BATTERY_KWH_MIN = 1.0e9

# Operational base scenario: rows used for Full vs Partial vs Greedy (EV) comparisons. Diesel-proxy battery excluded;
# for full_labeling / partial_labeling, interval / power / consumption must match when those columns are present.
BASE_SCENARIO_BATTERY_KWH = 750.0
BASE_SCENARIO_CS_INTERVAL_KM = 60.0
BASE_SCENARIO_CHARGING_POWER_KW = 350.0
BASE_SCENARIO_CONSUMPTION_KWH_PER_KM = 1.49

# Thesis-style Full vs Partial thresholds (match generate_thesis_full_vs_partial_tables.py)
THESIS_TIME_NOISE_MIN = 0.05
THESIS_SYNC_PP_NOISE = 0.05
THESIS_IDLE_NOISE_MIN = 0.05
THESIS_SOC_TOL_KWH = 0.5

# Diagnostic-style exports (match generate_diagnostic_tables.py)
DIAG_N_EXTREME_INSTANCES = 5
DIAG_NEAR_DIESEL_MAX_GAP_MIN = 15.0
DIAG_NEAR_DIESEL_MAX_COUNT = 6

# Column prefixes in table_summary_route_times_and_activity.csv
ROUTE_SUMMARY_STRAT_PREFIX = {
    "Full": "full",
    "Partial": "partial",
    "Greedy": "greedy",
    "Partial_Diesel_LB": "diesel_proxy",
}

# Drop these instances after load (same strings as instance_clean, i.e. instance_id with TB_ removed).
# Edit this tuple to control which tests are excluded from figures, tables, and the report.
EXCLUDED_INSTANCE_IDS: tuple[str, ...] = ()
# (
#     "short_cl2_cu2_Unbalanced",
#     "short_cl2_cu2_Balanced",
#     "long_cl3_cu4_Unbalanced",
# )


def _battery_kwh_from_row(row) -> float | None:
    for col in ("battery_capacity_kWh", "battery_capacity"):
        if hasattr(row, "index") and col not in row.index:
            continue
        v = row[col] if hasattr(row, "index") else row.get(col)
        if v is None or (isinstance(v, float) and np.isnan(v)):
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def load_csv(filepath):
    """Load CSV with correct column mapping. Handles duplicate columns and alternate names."""
    df = pd.read_csv(filepath, low_memory=False)
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
    return df


def get_strategy(row):
    """Map _runner_algorithm and _runner_tag to strategy name."""
    algo = str(row.get('_runner_algorithm', '')).lower()
    tag = str(row.get('_runner_tag', '')).lower()
    if tag == 'diesel_lb':
        return 'Partial_Diesel_LB' if 'partial' in algo else 'Greedy_Diesel_LB'
    if 'full' in algo:
        return 'Full'
    if 'partial' in algo:
        b = _battery_kwh_from_row(row)
        if b is not None and b >= DIESEL_PROXY_BATTERY_KWH_MIN:
            return 'Partial_Diesel_LB'
        return 'Partial'
    if 'greedy' in algo:
        return 'Greedy'
    return 'Other'


def get_problem_size(s):
    s = str(s).lower()
    if 'short' in s:
        return 'short'
    if 'med' in s:
        return 'medium'
    if 'long' in s:
        return 'large'
    return 'unknown'


def get_balance(s):
    """Instances without explicit Balanced/Unbalanced suffix are treated as Balanced."""
    s = str(s).lower()
    if 'unbalanced' in s:
        return 'Unbalanced'
    return 'Balanced'  # includes explicit _Balanced and those without suffix


# Left-to-right order on per-instance figures: short → medium → long, then instance name.
PROBLEM_SIZE_AXIS_ORDER = {'short': 0, 'medium': 1, 'large': 2}


def instance_sort_key(inst: str) -> tuple:
    return (PROBLEM_SIZE_AXIS_ORDER.get(get_problem_size(inst), 99), str(inst))


_INSTANCE_CODE_RE = re.compile(
    r"^(?P<h>short|med|long)_cl(?P<cl>\d+)_cu(?P<cu>\d+)(?:_(?P<bal>Balanced|Unbalanced))?$"
)


def derive_instance_plot_id(instance_clean: str) -> str:
    """Readable code tied to the test name, e.g. short_cl2_cu4_Unbalanced -> S_cl2_cu4_U."""
    s = str(instance_clean).strip()
    m = _INSTANCE_CODE_RE.match(s)
    if m:
        h = m.group("h")
        H = {"short": "S", "med": "M", "long": "L"}[h]
        cl = m.group("cl")
        cu = m.group("cu")
        bal = m.group("bal")
        tail = "U" if bal == "Unbalanced" else "B"
        return f"{H}_cl{cl}_cu{cu}_{tail}"
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_")
    return slug[:48] if slug else "inst"


def build_instance_id_map(
    base: pd.DataFrame, strat_data: dict | None = None
) -> pd.DataFrame:
    """Mnemonic ids for figures/tables; same instance order as charts (short→medium→long, then name)."""
    if strat_data is not None:
        instances = instances_from_strategies(strat_data)
    else:
        instances = sorted(base["instance_clean"].dropna().unique(), key=instance_sort_key)
    raw = [derive_instance_plot_id(str(i)) for i in instances]
    used: set[str] = set()
    ids: list[str] = []
    for c in raw:
        cand = c
        n = 0
        while cand in used:
            n += 1
            cand = f"{c}_{n}"
        used.add(cand)
        ids.append(cand)
    return pd.DataFrame({"id": ids, "instance_clean": instances})


def attach_instance_ids_to_comparisons(comp: dict, id_map_df: pd.DataFrame) -> dict:
    """Add column id to each merged comparison frame (inner join on instance_clean)."""
    if id_map_df is None or id_map_df.empty:
        return comp
    for key in ("full_vs_partial", "partial_vs_greedy", "partial_vs_diesel"):
        if key not in comp:
            continue
        m = comp[key]["merged"].copy()
        m = m.merge(id_map_df, on="instance_clean", how="left")
        if m["id"].isna().any():
            miss = m.loc[m["id"].isna(), "instance_clean"].astype(str).unique().tolist()
            raise ValueError(f"Instance ID map missing entries for: {miss}")
        m["id"] = m["id"].astype(str)
        comp[key]["merged"] = m
    return comp


def load_base_data():
    """Load base scenario only."""
    base_files = list(BASE_SCENARIO_DIR.glob("unified_results_*.csv"))
    if not base_files:
        base_dfs = [load_csv(f) for f in BASE_SCENARIO_DIR.glob("*.csv") if 'unified' not in f.name]
        base = pd.concat(base_dfs, ignore_index=True) if base_dfs else pd.DataFrame()
    else:
        base_files_sorted = sorted(base_files, key=lambda p: p.stat().st_mtime, reverse=True)
        base = load_csv(base_files_sorted[0])

    if not base.empty and '_runner_algorithm' in base.columns:
        algo = base['_runner_algorithm'].astype(str).str.lower()
        if not algo.str.contains('greedy', na=False).any():
            greedy_files = sorted(
                BASE_SCENARIO_DIR.glob('greedy_results_*.csv'),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if greedy_files:
                gpath = greedy_files[0]
                gdf = load_csv(gpath)
                base = pd.concat([base, gdf], ignore_index=True, sort=False)
                print(
                    f"Note: unified CSV has no greedy rows; appended {len(gdf)} rows from "
                    f"{gpath.name}. Re-export unified results including greedy for one consistent "
                    "cluster run id."
                )

    if base.empty:
        return base

    base['strategy'] = base.apply(get_strategy, axis=1)
    inst_col = 'instance_id' if 'instance_id' in base.columns else 'test_bed_id'
    base['instance_clean'] = base[inst_col].fillna(base.get('test_bed_id', '')).astype(str).str.replace('TB_', '')
    base['problem_size'] = base['instance_clean'].apply(get_problem_size)
    base['balance'] = base['instance_clean'].apply(get_balance)

    # Unified route time: total_route_time_hours (Full, Partial, Diesel) vs total_time (Greedy)
    if 'total_route_time_hours' in base.columns and 'total_time' in base.columns:
        base['route_time'] = base['total_route_time_hours'].fillna(base['total_time'])
    else:
        base['route_time'] = base.get('total_route_time_hours', base.get('total_time'))

    # Unified computation time
    base['comp_time_sec'] = base.get('computation_time_sec', base.get('computation_time', np.nan))

    # Charging sync counts from activity_timeline (if present)
    if 'activity_timeline' in base.columns:
        base = add_charging_sync_columns(base, 'activity_timeline')

    base = exclude_instances_from_base(base)
    return base


def exclude_instances_from_base(base: pd.DataFrame) -> pd.DataFrame:
    """Remove rows whose instance_clean is in EXCLUDED_INSTANCE_IDS."""
    if base.empty or not EXCLUDED_INSTANCE_IDS:
        return base
    if "instance_clean" not in base.columns:
        return base
    excl = set(EXCLUDED_INSTANCE_IDS)
    present = sorted(excl & set(base["instance_clean"].astype(str).unique()))
    n_inst_before = base["instance_clean"].nunique()
    out = base[~base["instance_clean"].isin(excl)].copy()
    n_inst_after = out["instance_clean"].nunique()
    if present:
        print(
            f"Excluded {len(present)} instance(s) from analysis: {', '.join(present)} "
            f"({n_inst_before} -> {n_inst_after} instances, {len(base)} -> {len(out)} rows)"
        )
    return out


# --- Four main strategies for analysis ---
STRATEGIES = ['Full', 'Partial', 'Greedy', 'Partial_Diesel_LB']
STRATEGY_LABELS = {'Full': 'Full Recharge', 'Partial': 'Partial Recharge', 'Greedy': 'Greedy',
                   'Partial_Diesel_LB': 'Diesel proxy (high battery)'}


def _numeric_series(df: pd.DataFrame, candidates: tuple[str, ...]) -> pd.Series | None:
    for c in candidates:
        if c in df.columns:
            return pd.to_numeric(df[c], errors="coerce")
    return None


def base_scenario_ev_mask(df: pd.DataFrame) -> pd.Series:
    """
    True for rows that belong to the operational EV base scenario used for Full / Partial / Greedy.
    Excludes diesel-proxy battery (>= DIESEL_PROXY_BATTERY_KWH_MIN) and, for full/partial_labeling only,
    requires CS interval, charging power, and consumption to match BASE_SCENARIO_* when those columns exist.
    Greedy rows are not subject to the labeling-only parameter checks (so older greedy CSVs still work).
    """
    if df.empty:
        return pd.Series(dtype=bool, index=df.index)
    idx = df.index
    m = pd.Series(True, index=idx)
    b = _numeric_series(df, ("battery_capacity_kWh", "battery_capacity"))
    if b is not None:
        m &= b.isna() | (
            (b < DIESEL_PROXY_BATTERY_KWH_MIN)
            & np.isclose(b, BASE_SCENARIO_BATTERY_KWH, rtol=0.0, atol=0.51)
        )
    algo = (
        df["_runner_algorithm"].astype(str).str.lower()
        if "_runner_algorithm" in df.columns
        else pd.Series("", index=idx)
    )
    is_labeling = algo.str.contains("full_labeling", na=False) | algo.str.contains(
        "partial_labeling", na=False
    )
    v = _numeric_series(df, ("charging_station_interval_km", "distance_per_cs"))
    if v is not None:
        m &= ~is_labeling | v.isna() | np.isclose(
            v, BASE_SCENARIO_CS_INTERVAL_KM, rtol=0.0, atol=1e-4
        )
    v = _numeric_series(df, ("charging_power_kW", "charging_power"))
    if v is not None:
        m &= ~is_labeling | v.isna() | np.isclose(
            v, BASE_SCENARIO_CHARGING_POWER_KW, rtol=0.0, atol=1e-4
        )
    v = _numeric_series(df, ("energy_consumption_rate_kWh_per_km", "consumption_rate"))
    if v is not None:
        m &= ~is_labeling | v.isna() | np.isclose(
            v, BASE_SCENARIO_CONSUMPTION_KWH_PER_KM, rtol=0.0, atol=1e-6
        )
    return m


def build_strat_data(base: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    One row per instance per strategy. Full / Partial / Greedy use only base-scenario EV rows;
    Partial_Diesel_LB uses all diesel-proxy partial rows (large battery), regardless of EV mask.
    """
    ev_mask = base_scenario_ev_mask(base)
    base_ev = base.loc[ev_mask]
    out: dict[str, pd.DataFrame] = {}
    for s in ("Full", "Partial", "Greedy"):
        sub = base_ev[base_ev["strategy"] == s].drop_duplicates("instance_clean", keep="first")
        out[s] = sub
    sub = base.loc[base["strategy"] == "Partial_Diesel_LB"].drop_duplicates(
        "instance_clean", keep="first"
    )
    out["Partial_Diesel_LB"] = sub
    return out


def instances_from_strategies(strat_data: dict) -> list:
    """Union of instance_clean across all strategy tables, sorted like main charts."""
    insts: set[str] = set()
    for s in STRATEGIES:
        d = strat_data.get(s)
        if d is not None and not d.empty and "instance_clean" in d.columns:
            insts.update(d["instance_clean"].dropna().astype(str).unique())
    return sorted(insts, key=instance_sort_key)


def get_strategy_data(base):
    """Return dict: strategy -> DataFrame (one row per instance). Same as build_strat_data."""
    return build_strat_data(base)


def route_summary_config_caption() -> str:
    """Human-readable caption for reports and markdown (EV labeling configuration)."""
    return (
        f"battery {BASE_SCENARIO_BATTERY_KWH:g} kWh, CS spacing {BASE_SCENARIO_CS_INTERVAL_KM:g} km, "
        f"charging power {BASE_SCENARIO_CHARGING_POWER_KW:g} kW, consumption "
        f"{BASE_SCENARIO_CONSUMPTION_KWH_PER_KM:g} kWh/km. "
        "Diesel proxy = partial_labeling with very large battery (unconstrained lower bound). "
        "Greedy uses the appended/unified greedy run parameters (may differ if greedy comes from another export)."
    )


def _first_series_value(s: pd.Series, candidates: tuple[str, ...]):
    for c in candidates:
        if c in s.index:
            v = s.get(c)
            if pd.notna(v):
                return v
    return np.nan


def build_route_activity_summary(
    strat_data: dict, id_map_df: pd.DataFrame | None
) -> pd.DataFrame:
    """
    One row per instance: route time and activity/sync metrics for Full, Partial, Greedy, diesel proxy.
    Uses strat_data rows (already EV-filtered for F/P/G; diesel from large-battery partials).
    """
    instances = instances_from_strategies(strat_data)
    id_by: dict[str, str] = {}
    if id_map_df is not None and not id_map_df.empty:
        id_by = dict(zip(id_map_df["instance_clean"].astype(str), id_map_df["id"].astype(str)))

    metric_defs: list[tuple[str, tuple[str, ...]]] = [
        ("route_h", ("route_time",)),
        ("n_cs_stops", ("number_of_cs_stops", "num_charges")),
        ("n_breaks", ("number_of_breaks", "num_breaks")),
        ("n_rests", ("number_of_rests", "num_rests")),
        ("n_charges", ("num_charges",)),
        ("n_sync_events", ("number_of_synchronized_events", "num_synchronized_events")),
        ("pct_charge_sync", ("percentage_of_charging_events_synchronized",)),
        ("n_sync_charges", ("num_synchronized",)),
        ("n_unsync_charges", ("num_unsynchronized",)),
        ("n_sync_w_break", ("num_sync_with_break",)),
        ("n_sync_w_rest", ("num_sync_with_rest",)),
    ]

    rows: list[dict] = []
    for inst in instances:
        row: dict = {"instance": inst, "id": id_by.get(str(inst), "")}
        for strat_name, pfx in ROUTE_SUMMARY_STRAT_PREFIX.items():
            sd = strat_data.get(strat_name)
            if sd is None or sd.empty:
                for suffix, _ in metric_defs:
                    row[f"{pfx}_{suffix}"] = np.nan
                continue
            sub = sd[sd["instance_clean"] == inst]
            if sub.empty:
                for suffix, _ in metric_defs:
                    row[f"{pfx}_{suffix}"] = np.nan
                continue
            ser = sub.iloc[0]
            for suffix, candidates in metric_defs:
                v = _first_series_value(ser, candidates)
                if suffix == "route_h" and pd.notna(v):
                    row[f"{pfx}_{suffix}"] = round(float(v), 4)
                elif suffix == "pct_charge_sync" and pd.notna(v):
                    row[f"{pfx}_{suffix}"] = round(float(v), 3)
                elif pd.notna(v):
                    try:
                        row[f"{pfx}_{suffix}"] = int(round(float(v)))
                    except (TypeError, ValueError):
                        row[f"{pfx}_{suffix}"] = v
                else:
                    row[f"{pfx}_{suffix}"] = np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def _df_to_pipe_markdown(df: pd.DataFrame) -> str:
    cols = "| " + " | ".join(str(c) for c in df.columns) + " |"
    sep = "| " + " | ".join(["---"] * len(df.columns)) + " |"
    out = [cols, sep]
    for _, r in df.iterrows():
        out.append("| " + " | ".join("" if pd.isna(x) else str(x) for x in r) + " |")
    return "\n".join(out)


def _safe_dataframe_to_csv(df: pd.DataFrame, path: Path, *, index: bool = False) -> Path:
    """Write CSV; on PermissionError (e.g. file open in Excel / OneDrive lock), use a timestamped file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_csv(path, index=index)
        return path
    except PermissionError:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        alt = path.with_name(f"{path.stem}_write_{ts}{path.suffix}")
        try:
            df.to_csv(alt, index=index)
        except PermissionError as e:
            raise PermissionError(
                f"Could not write {path.name} or {alt.name}; close programs locking these files and retry."
            ) from e
        print(
            f"Note: could not overwrite {path.name} (file open or locked). Wrote {alt.name} instead.",
            file=sys.stderr,
        )
        return alt


def _safe_path_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(text, encoding=encoding)
        return path
    except PermissionError:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        alt = path.with_name(f"{path.stem}_write_{ts}{path.suffix}")
        try:
            alt.write_text(text, encoding=encoding)
        except PermissionError as e:
            raise PermissionError(
                f"Could not write {path.name} or {alt.name}; close programs locking these files and retry."
            ) from e
        print(
            f"Note: could not overwrite {path.name} (file open or locked). Wrote {alt.name} instead.",
            file=sys.stderr,
        )
        return alt


def write_route_activity_summary_markdown(summary_df: pd.DataFrame, path: Path) -> None:
    """Markdown with caption + route-time preview; full wide data stays in the CSV."""
    lines = [
        "# Summary: route times, stops, breaks, rests, charging & synchronization",
        "",
        "**Configuration for EV labeling (Full & Partial columns in this project):**",
        route_summary_config_caption(),
        "",
        "Greedy / diesel-proxy columns use the corresponding run parameters. "
        "Timeline-derived charging/sync fields are blank when `activity_timeline` was missing.",
        "",
        "Wide CSV column names: `{strategy}_{metric}` with strategies "
        "`full`, `partial`, `greedy`, `diesel_proxy`.",
        "",
        "## Route times (hours) — preview",
        "",
    ]
    route_cols = [
        "instance",
        "id",
        "full_route_h",
        "partial_route_h",
        "greedy_route_h",
        "diesel_proxy_route_h",
    ]
    slim = summary_df[[c for c in route_cols if c in summary_df.columns]]
    if not slim.empty:
        try:
            lines.append(slim.to_markdown(index=False))
        except (ImportError, ValueError):
            lines.append(_df_to_pipe_markdown(slim))
    lines.extend(
        [
            "",
            "## Full table",
            "",
            "All metrics per strategy (CS stops, breaks, rests, charges, sync counts, % sync): "
            "**`table_summary_route_times_and_activity.csv`**",
        ]
    )
    text = "\n".join(lines)
    _safe_path_write_text(path, text)


# --- Analyst CSV tables (thesis + diagnostic numerics; no long diagnostic prose) ---


def _row_float(ser: pd.Series, col: str):
    if col not in ser.index:
        return None
    v = ser[col]
    if pd.isna(v):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _row_int(ser: pd.Series, col: str, default: int = 0) -> int:
    if col not in ser.index:
        return default
    v = ser[col]
    if pd.isna(v):
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _is_exact_soc(mn: float, mx: float) -> bool:
    return abs(mx - mn) < 1e-6


def _fmt_soc_effect_thesis(full: dict, partial: dict) -> str:
    def _f(x, default=None):
        if x is None:
            return default
        try:
            return float(x)
        except (TypeError, ValueError):
            return default

    fmin = _f(full.get("final_battery_energy_min_kWh"))
    fmax = _f(full.get("final_battery_energy_max_kWh"))
    pmin = _f(partial.get("final_battery_energy_min_kWh"))
    pmax = _f(partial.get("final_battery_energy_max_kWh"))
    if any(v is None for v in (fmin, fmax, pmin, pmax)):
        return "N/A"
    if max(abs(fmin), abs(fmax), abs(pmin), abs(pmax)) > 1e6:
        return "N/A"

    full_ex = _is_exact_soc(fmin, fmax)
    part_ex = _is_exact_soc(pmin, pmax)

    if full_ex and part_ex:
        if abs(fmin - pmin) <= THESIS_SOC_TOL_KWH and abs(fmax - pmax) <= THESIS_SOC_TOL_KWH:
            return "No change"
        diff = pmin - fmin
        if abs(diff) <= THESIS_SOC_TOL_KWH:
            return "No change"
        if diff > 0:
            return f"Partial ends with {round(diff, 1)} kWh more SOC"
        return f"Partial ends with {round(-diff, 1)} kWh less SOC"

    if full_ex and not part_ex:
        return (
            f"Partial ends with SOC range {round(pmin, 1)}–{round(pmax, 1)} kWh "
            f"vs fixed Full {round(fmin, 1)} kWh"
        )

    if not full_ex and part_ex:
        return f"Full range {round(fmin, 1)}–{round(fmax, 1)} kWh vs Partial {round(pmin, 1)} kWh"

    return (
        f"Partial range {round(pmin, 1)}–{round(pmax, 1)} kWh vs Full "
        f"{round(fmin, 1)}–{round(fmax, 1)} kWh"
    )


def _short_interpretation_thesis(
    delta_min: float,
    d_sync: float,
    d_unsync: int,
    d_idle: float,
    soc_txt: str,
) -> str:
    t_same = abs(delta_min) < THESIS_TIME_NOISE_MIN
    s_same = (
        abs(d_sync) < THESIS_SYNC_PP_NOISE
        and d_unsync == 0
        and abs(d_idle) < THESIS_IDLE_NOISE_MIN
    )
    soc_same = soc_txt == "No change"
    sync_better = (
        (d_sync > THESIS_SYNC_PP_NOISE)
        or d_unsync < 0
        or d_idle < -THESIS_IDLE_NOISE_MIN
    )
    sync_worse = (
        (d_sync < -THESIS_SYNC_PP_NOISE)
        or d_unsync > 0
        or d_idle > THESIS_IDLE_NOISE_MIN
    )
    t_faster = delta_min < -THESIS_TIME_NOISE_MIN
    t_slower = delta_min > THESIS_TIME_NOISE_MIN
    interval_soc = "range" in soc_txt.lower()

    if t_same and s_same and soc_same:
        return "Identical outcome"
    if t_faster and sync_better and not interval_soc:
        return "Partial improves time and synchronization"
    if t_faster and sync_better and interval_soc:
        return "Partial improves time and sync; interval SOC"
    if t_same and sync_better and soc_same:
        return "Partial improves synchronization only"
    if t_same and sync_better and interval_soc:
        return "Partial improves synchronization but returns interval SOC"
    if t_same and s_same and interval_soc:
        return "Partial gives same time but more flexible SOC outcome"
    if t_faster and s_same and interval_soc:
        return "Partial faster; interval SOC vs fixed Full"
    if t_faster and s_same and soc_same:
        return "Partial faster; sync and SOC comparable"
    if t_slower and sync_better:
        return "Partial slower but better synchronization"
    if t_slower and s_same:
        return "Partial slower; sync comparable"
    if sync_worse and t_faster:
        return "Partial faster despite weaker sync metrics"
    return "Mixed effects"


def _route_class(instance_id: str) -> str:
    s = str(instance_id).lower()
    if s.startswith("short"):
        return "Short"
    if s.startswith("med"):
        return "Medium"
    if s.startswith("long"):
        return "Long"
    return "Other"


def merge_full_partial_strat(strat_data: dict) -> pd.DataFrame:
    """Inner join EV Full and Partial rows (one row per instance)."""
    full = strat_data.get("Full")
    partial = strat_data.get("Partial")
    if full is None or partial is None or full.empty or partial.empty:
        return pd.DataFrame()
    key = "instance_clean"
    return full.merge(partial, on=key, how="inner", suffixes=("_full", "_partial"))


def _diag_metrics_from_merged_row(row: pd.Series, side: str) -> dict:
    """side is 'full' or 'partial' -> merged columns end with _full or _partial."""
    suf = "_full" if side == "full" else "_partial"
    out: dict = {"route_h": None}
    rt_c = f"route_time{suf}"
    if rt_c in row.index and pd.notna(row[rt_c]):
        try:
            out["route_h"] = float(row[rt_c])
        except (TypeError, ValueError):
            pass
    for base, key in [
        ("percentage_of_charging_events_synchronized", "sync_pct"),
        ("number_of_unsynchronized_charging_events", "unsync_chg"),
        ("total_idle_charging_time_minutes", "idle_min"),
        ("number_of_synchronized_events", "sync_ev"),
        ("number_of_cs_stops", "cs_stops"),
        ("number_of_breaks", "breaks"),
        ("number_of_rests", "rests"),
        ("number_of_rest_synchronized_charging_events", "rest_sync_chg"),
        ("number_of_break_fully_synchronized_charging_events", "break_full_sync"),
        ("number_of_break_partial_synchronized_charging_events", "break_part_sync"),
        ("number_of_break_synchronized_charging_events", "break_any_sync"),
        ("number_of_unsynchronized_breaks", "unsync_breaks"),
        ("number_of_unsynchronized_rests", "unsync_rests"),
    ]:
        cn = f"{base}{suf}"
        if cn in row.index and pd.notna(row[cn]):
            try:
                out[key] = float(row[cn]) if key in ("sync_pct", "idle_min") else int(row[cn])
            except (TypeError, ValueError):
                out[key] = None
        else:
            out[key] = None
    return out


def build_thesis_full_partial_per_instance(strat_data: dict, id_map_df: pd.DataFrame | None) -> pd.DataFrame:
    """Numeric + short labels per instance (same deltas as generate_thesis_full_vs_partial_tables)."""
    m = merge_full_partial_strat(strat_data)
    if m.empty:
        return pd.DataFrame()

    id_by: dict[str, str] = {}
    if id_map_df is not None and not id_map_df.empty:
        id_by = dict(zip(id_map_df["instance_clean"].astype(str), id_map_df["id"].astype(str)))

    rows: list[dict] = []
    for _, row in m.iterrows():
        inst = str(row["instance_clean"])
        rf = _row_float(row, "route_time_full")
        rp = _row_float(row, "route_time_partial")
        if rf is None or rp is None:
            continue
        delta_min = (rp - rf) * 60.0
        sf = _row_float(row, "percentage_of_charging_events_synchronized_full") or 0.0
        sp = _row_float(row, "percentage_of_charging_events_synchronized_partial") or 0.0
        d_sync = sp - sf
        uf = _row_int(row, "number_of_unsynchronized_charging_events_full")
        up = _row_int(row, "number_of_unsynchronized_charging_events_partial")
        d_unsync = up - uf
        idle_f = _row_float(row, "total_idle_charging_time_minutes_full") or 0.0
        idle_p = _row_float(row, "total_idle_charging_time_minutes_partial") or 0.0
        d_idle = idle_p - idle_f

        full_d: dict = {"total_route_time_hours": rf}
        partial_d: dict = {"total_route_time_hours": rp}
        for _k in (
            "final_battery_energy_min_kWh",
            "final_battery_energy_max_kWh",
        ):
            cf, cp = f"{_k}_full", f"{_k}_partial"
            if cf in row.index:
                full_d[_k] = row[cf]
            if cp in row.index:
                partial_d[_k] = row[cp]
        soc_txt = _fmt_soc_effect_thesis(full_d, partial_d)
        interp = _short_interpretation_thesis(delta_min, d_sync, d_unsync, d_idle, soc_txt)

        mf = _diag_metrics_from_merged_row(row, "full")
        mp = _diag_metrics_from_merged_row(row, "partial")

        rows.append(
            {
                "instance_clean": inst,
                "id": id_by.get(inst, ""),
                "route_class": _route_class(inst),
                "delta_route_partial_minus_full_min": round(delta_min, 4),
                "benefit_full_minus_partial_min": round((rf - rp) * 60.0, 4),
                "full_route_h": round(rf, 4),
                "partial_route_h": round(rp, 4),
                "d_sync_pct_points": round(d_sync, 4),
                "d_unsync_charging_events": d_unsync,
                "d_idle_charging_min": round(d_idle, 4),
                "full_sync_pct": round(sf, 3) if sf is not None else None,
                "partial_sync_pct": round(sp, 3) if sp is not None else None,
                "full_unsync_chg": uf,
                "partial_unsync_chg": up,
                "idle_charging_min_full": round(idle_f, 3),
                "idle_charging_min_partial": round(idle_p, 3),
                "full_cs_stops": mf.get("cs_stops"),
                "partial_cs_stops": mp.get("cs_stops"),
                "full_breaks": mf.get("breaks"),
                "partial_breaks": mp.get("breaks"),
                "full_rests": mf.get("rests"),
                "partial_rests": mp.get("rests"),
                "full_n_charges_tl": (
                    int(row["num_charges_full"])
                    if "num_charges_full" in row.index and pd.notna(row["num_charges_full"])
                    else None
                ),
                "partial_n_charges_tl": (
                    int(row["num_charges_partial"])
                    if "num_charges_partial" in row.index and pd.notna(row["num_charges_partial"])
                    else None
                ),
                "soc_effect": soc_txt,
                "interpretation_short": interp,
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.copy()
        df["_sk"] = df["instance_clean"].map(lambda i: instance_sort_key(str(i)))
        df = df.sort_values("_sk").drop(columns="_sk")
    return df


def build_thesis_full_partial_by_route_class(per_inst: pd.DataFrame) -> pd.DataFrame:
    if per_inst.empty or "route_class" not in per_inst.columns:
        return pd.DataFrame()
    order = ["Short", "Medium", "Long", "Other"]
    out_rows: list[dict] = []
    for g in order:
        gr = per_inst[per_inst["route_class"] == g]
        if gr.empty:
            continue
        n = len(gr)
        out_rows.append(
            {
                "route_class": g,
                "n_instances": n,
                "mean_delta_partial_minus_full_min": round(gr["delta_route_partial_minus_full_min"].mean(), 4),
                "mean_d_sync_pct_points": round(gr["d_sync_pct_points"].mean(), 4),
                "mean_d_unsync_charging_events": round(gr["d_unsync_charging_events"].mean(), 4),
                "mean_d_idle_charging_min": round(gr["d_idle_charging_min"].mean(), 4),
                "mean_full_route_h": round(gr["full_route_h"].mean(), 4),
                "mean_partial_route_h": round(gr["partial_route_h"].mean(), 4),
                "mean_benefit_full_minus_partial_min": round(gr["benefit_full_minus_partial_min"].mean(), 4),
            }
        )
    return pd.DataFrame(out_rows)


def build_diagnostic_partial_full_extremes(per_inst: pd.DataFrame) -> pd.DataFrame:
    """Top / bottom instances by (Full − Partial) route time in minutes (Partial time saved)."""
    if per_inst.empty or "benefit_full_minus_partial_min" not in per_inst.columns:
        return pd.DataFrame()
    d = per_inst.sort_values("benefit_full_minus_partial_min", ascending=False).reset_index(drop=True)
    n = DIAG_N_EXTREME_INSTANCES
    top = d.head(n).copy()
    top["extreme_tier"] = "most_partial_time_advantage"
    bot = d.tail(n).iloc[::-1].copy()
    bot["extreme_tier"] = "least_partial_time_advantage"
    cols = [
        "extreme_tier",
        "instance_clean",
        "id",
        "benefit_full_minus_partial_min",
        "delta_route_partial_minus_full_min",
        "full_route_h",
        "partial_route_h",
        "full_sync_pct",
        "partial_sync_pct",
        "d_sync_pct_points",
        "full_unsync_chg",
        "partial_unsync_chg",
        "d_unsync_charging_events",
        "idle_charging_min_full",
        "idle_charging_min_partial",
        "d_idle_charging_min",
        "full_cs_stops",
        "partial_cs_stops",
        "full_breaks",
        "partial_breaks",
    ]
    cols = [c for c in cols if c in top.columns]
    return pd.concat([top[cols], bot[cols]], ignore_index=True)


def build_diagnostic_near_diesel_wide(strat_data: dict, id_map_df: pd.DataFrame | None) -> pd.DataFrame:
    """Instances where |EV partial − diesel proxy| route time ≤ threshold (minutes)."""
    pe = strat_data.get("Partial")
    pdsl = strat_data.get("Partial_Diesel_LB")
    if pe is None or pdsl is None or pe.empty or pdsl.empty:
        return pd.DataFrame()

    m = pe.merge(pdsl, on="instance_clean", how="inner", suffixes=("_ev", "_diesel"))
    if m.empty:
        return pd.DataFrame()

    id_by: dict[str, str] = {}
    if id_map_df is not None and not id_map_df.empty:
        id_by = dict(zip(id_map_df["instance_clean"].astype(str), id_map_df["id"].astype(str)))

    m["gap_abs_route_min"] = (
        (m["route_time_ev"] - m["route_time_diesel"]).abs() * 60.0
    )
    m = m[m["gap_abs_route_min"] <= DIAG_NEAR_DIESEL_MAX_GAP_MIN].sort_values(
        "gap_abs_route_min"
    ).head(DIAG_NEAR_DIESEL_MAX_COUNT)

    def pick(row, col_ev: str, col_d: str):
        ve = row[col_ev] if col_ev in row.index else np.nan
        vd = row[col_d] if col_d in row.index else np.nan
        return ve, vd

    metric_pairs = [
        ("route_h", "route_time_ev", "route_time_diesel"),
        ("sync_pct", "percentage_of_charging_events_synchronized_ev", "percentage_of_charging_events_synchronized_diesel"),
        ("unsync_chg", "number_of_unsynchronized_charging_events_ev", "number_of_unsynchronized_charging_events_diesel"),
        ("idle_min", "total_idle_charging_time_minutes_ev", "total_idle_charging_time_minutes_diesel"),
        ("sync_ev", "number_of_synchronized_events_ev", "number_of_synchronized_events_diesel"),
        ("cs_stops", "number_of_cs_stops_ev", "number_of_cs_stops_diesel"),
        ("breaks", "number_of_breaks_ev", "number_of_breaks_diesel"),
        ("rests", "number_of_rests_ev", "number_of_rests_diesel"),
        ("rest_sync_chg", "number_of_rest_synchronized_charging_events_ev", "number_of_rest_synchronized_charging_events_diesel"),
        ("break_full_sync", "number_of_break_fully_synchronized_charging_events_ev", "number_of_break_fully_synchronized_charging_events_diesel"),
        ("break_part_sync", "number_of_break_partial_synchronized_charging_events_ev", "number_of_break_partial_synchronized_charging_events_diesel"),
        ("break_any_sync", "number_of_break_synchronized_charging_events_ev", "number_of_break_synchronized_charging_events_diesel"),
        ("unsync_breaks", "number_of_unsynchronized_breaks_ev", "number_of_unsynchronized_breaks_diesel"),
        ("unsync_rests", "number_of_unsynchronized_rests_ev", "number_of_unsynchronized_rests_diesel"),
    ]

    rows: list[dict] = []
    for _, row in m.iterrows():
        inst = str(row["instance_clean"])
        out: dict = {
            "instance_clean": inst,
            "id": id_by.get(inst, ""),
            "gap_abs_route_min": round(float(row["gap_abs_route_min"]), 4),
            "ev_minus_diesel_route_min": round(
                float(row["route_time_ev"] - row["route_time_diesel"]) * 60.0, 4
            ),
        }
        for short, ce, cd in metric_pairs:
            if ce not in row.index or cd not in row.index:
                out[f"ev_{short}"] = np.nan
                out[f"diesel_{short}"] = np.nan
                out[f"delta_ev_minus_diesel_{short}"] = np.nan
                continue
            ve, vd = row[ce], row[cd]
            out[f"ev_{short}"] = ve
            out[f"diesel_{short}"] = vd
            if pd.notna(ve) and pd.notna(vd):
                int_metrics = (
                    "unsync_chg",
                    "sync_ev",
                    "cs_stops",
                    "breaks",
                    "rests",
                    "rest_sync_chg",
                    "break_full_sync",
                    "break_part_sync",
                    "break_any_sync",
                    "unsync_breaks",
                    "unsync_rests",
                )
                if short in int_metrics:
                    out[f"delta_ev_minus_diesel_{short}"] = int(round(float(ve))) - int(
                        round(float(vd))
                    )
                else:
                    out[f"delta_ev_minus_diesel_{short}"] = round(float(ve) - float(vd), 6)
            else:
                out[f"delta_ev_minus_diesel_{short}"] = np.nan
        rows.append(out)
    return pd.DataFrame(rows)


def save_thesis_diagnostic_analyst_tables(
    strat_data: dict, tbl_dir: Path, id_map_df: pd.DataFrame | None
) -> None:
    """CSV tables aligned with thesis / diagnostic scripts (for your own analysis)."""
    per = build_thesis_full_partial_per_instance(strat_data, id_map_df)
    if per.empty:
        return
    _safe_dataframe_to_csv(per, tbl_dir / "table_thesis_full_vs_partial_per_instance.csv", index=False)
    by_cls = build_thesis_full_partial_by_route_class(per)
    if not by_cls.empty:
        _safe_dataframe_to_csv(by_cls, tbl_dir / "table_thesis_full_vs_partial_by_route_class.csv", index=False)
    ex = build_diagnostic_partial_full_extremes(per)
    if not ex.empty:
        _safe_dataframe_to_csv(ex, tbl_dir / "table_diagnostic_partial_vs_full_extremes.csv", index=False)
    near = build_diagnostic_near_diesel_wide(strat_data, id_map_df)
    if not near.empty:
        _safe_dataframe_to_csv(near, tbl_dir / "table_diagnostic_near_diesel_wide.csv", index=False)

    cap = (
        f"EV Full/Partial configuration: {route_summary_config_caption()} "
        f"Extremes: top/bottom {DIAG_N_EXTREME_INSTANCES} by benefit_full_minus_partial_min (minutes). "
        f"Near-diesel: |EV−diesel| route ≤ {DIAG_NEAR_DIESEL_MAX_GAP_MIN:.0f} min, up to {DIAG_NEAR_DIESEL_MAX_COUNT} instances."
    )
    _safe_path_write_text(tbl_dir / "table_thesis_diagnostic_caption.txt", cap + "\n")


def _sort_merged_instances_like_main_chart(m: pd.DataFrame) -> pd.DataFrame:
    """Same order as Figure 01 (short → medium → long, then name)."""
    m = m.copy()
    m['_ord'] = m['instance_clean'].map(lambda i: instance_sort_key(str(i)))
    m = m.sort_values('_ord').drop(columns='_ord').reset_index(drop=True)
    return m


def _partial_advantage_avg_min_max_display(
    adv_pct: pd.Series, delta_h_benchmark_minus_partial: pd.Series
) -> tuple[str, str, str]:
    """
    adv_pct: 100 * (t_benchmark - t_partial) / t_benchmark per instance.
    delta_h: (t_benchmark - t_partial) in hours; minutes column = delta_h * 60.

    Average row: mean(%) and mean(minutes) over instances.

    Minimum / maximum rows: instances with smallest / largest *route-time saving in minutes*
    (not smallest/largest %). Then the % shown is that instance's %. This guarantees
    min_minutes <= mean_minutes <= max_minutes; previously min/max used % extrema, which
    broke that ordering when % and absolute time did not rank the same way.
    """
    dm = delta_h_benchmark_minus_partial * 60.0
    avg_s = f"{float(adv_pct.mean()):.2f}% ({float(dm.mean()):.2f} min)"
    ix_lo = dm.idxmin()
    ix_hi = dm.idxmax()
    min_s = f"{float(adv_pct.loc[ix_lo]):.2f}% ({float(dm.loc[ix_lo]):.2f} min)"
    max_s = f"{float(adv_pct.loc[ix_hi]):.2f}% ({float(dm.loc[ix_hi]):.2f} min)"
    return avg_s, min_s, max_s


def compute_comparisons(base, strat_data):
    """Compute Full vs Partial, Partial vs Greedy, Partial vs Diesel LB with all four in scope."""
    comp = {}
    full = strat_data.get('Full')
    partial = strat_data.get('Partial')
    greedy = strat_data.get('Greedy')
    diesel = strat_data.get('Partial_Diesel_LB')

    if not full.empty and not partial.empty:
        m = partial.merge(full[['instance_clean', 'route_time']], on='instance_clean', suffixes=('_p', '_f'), how='inner')
        if len(m) > 0:
            m = _sort_merged_instances_like_main_chart(m)
            pt, pf = m['route_time_p'], m['route_time_f']
            adv_fp = (pf - pt) / pf * 100
            delta_fp = pf - pt
            dm_fp = delta_fp * 60.0
            adv_avg_s, adv_min_s, adv_max_s = _partial_advantage_avg_min_max_display(adv_fp, delta_fp)
            ix_lo_m, ix_hi_m = dm_fp.idxmin(), dm_fp.idxmax()
            comp['full_vs_partial'] = {
                'n': len(m), 'partial_better': (pt < pf).sum(), 'full_better': (pf < pt).sum(),
                'mean_partial': pt.mean(), 'mean_full': pf.mean(),
                'avg_improvement': adv_fp.mean(),
                'min_partial_advantage_pct': float(adv_fp.loc[ix_lo_m]),
                'max_partial_advantage_pct': float(adv_fp.loc[ix_hi_m]),
                'partial_advantage_avg': adv_avg_s,
                'partial_advantage_min': adv_min_s,
                'partial_advantage_max': adv_max_s,
                'merged': m,
            }

    if not partial.empty and not greedy.empty:
        m = partial.merge(greedy[['instance_clean', 'route_time']], on='instance_clean', suffixes=('_p', '_g'), how='inner')
        if len(m) > 0:
            m = _sort_merged_instances_like_main_chart(m)
            pt, pg = m['route_time_p'], m['route_time_g']
            adv_pg = (pg - pt) / pg * 100
            delta_pg = pg - pt
            dm_pg = delta_pg * 60.0
            adv_avg_s, adv_min_s, adv_max_s = _partial_advantage_avg_min_max_display(adv_pg, delta_pg)
            ix_lo_m, ix_hi_m = dm_pg.idxmin(), dm_pg.idxmax()
            comp['partial_vs_greedy'] = {
                'n': len(m), 'partial_better': (pt < pg).sum(), 'greedy_better': (pg < pt).sum(),
                'mean_partial': pt.mean(), 'mean_greedy': pg.mean(),
                'avg_improvement': adv_pg.mean(),
                'min_partial_advantage_pct': float(adv_pg.loc[ix_lo_m]),
                'max_partial_advantage_pct': float(adv_pg.loc[ix_hi_m]),
                'partial_advantage_avg': adv_avg_s,
                'partial_advantage_min': adv_min_s,
                'partial_advantage_max': adv_max_s,
                'merged': m,
            }

    if not partial.empty and not diesel.empty:
        m = partial.merge(diesel[['instance_clean', 'route_time']], on='instance_clean', suffixes=('_p', '_d'), how='inner')
        if len(m) > 0:
            m = _sort_merged_instances_like_main_chart(m)
            pt, pd_ = m['route_time_p'], m['route_time_d']
            adv_diesel = (pd_ - pt) / pd_ * 100
            delta_diesel = pd_ - pt
            dm_diesel = delta_diesel * 60.0
            adv_avg_s, adv_min_s, adv_max_s = _partial_advantage_avg_min_max_display(adv_diesel, delta_diesel)
            ix_lo_m, ix_hi_m = dm_diesel.idxmin(), dm_diesel.idxmax()
            comp['partial_vs_diesel'] = {
                'n': len(m),
                'partial_faster': (pt < pd_).sum(),
                'diesel_faster': (pd_ < pt).sum(),
                'gap_pct': ((pt - pd_) / pd_ * 100).mean(),
                'mean_partial': pt.mean(),
                'mean_diesel': pd_.mean(),
                'min_partial_advantage_pct': float(adv_diesel.loc[ix_lo_m]),
                'max_partial_advantage_pct': float(adv_diesel.loc[ix_hi_m]),
                'partial_advantage_avg': adv_avg_s,
                'partial_advantage_min': adv_min_s,
                'partial_advantage_max': adv_max_s,
                'merged': m,
            }

    return comp


def by_problem_size_and_balance(base, strat_data):
    """Mean route time (Partial vs Full) by problem size and by balance."""
    partial = strat_data.get('Partial')
    full = strat_data.get('Full')
    if partial.empty or full.empty:
        return pd.DataFrame(), pd.DataFrame()

    part_cols = ['instance_clean', 'route_time', 'problem_size', 'balance']
    full_cols = ['instance_clean', 'route_time']
    merged = partial[[c for c in part_cols if c in partial.columns]].merge(
        full[full_cols], on='instance_clean', suffixes=('_p', '_f'), how='inner'
    )
    if merged.empty:
        return pd.DataFrame(), pd.DataFrame()

    pt = merged['route_time_p'] if 'route_time_p' in merged.columns else merged['route_time']
    pf = merged['route_time_f'] if 'route_time_f' in merged.columns else merged['route_time']

    size_rows = []
    for sz in ['short', 'medium', 'large']:
        sub = merged[merged['problem_size'] == sz]
        if len(sub) > 0:
            pt_s, pf_s = sub['route_time_p'], sub['route_time_f']
            size_rows.append({
                'size': sz, 'n': len(sub),
                'partial_better': (pt_s < pf_s).sum(), 'full_better': (pf_s < pt_s).sum(),
                'avg_improvement': ((pf_s - pt_s) / pf_s * 100).mean(),
                'mean_partial': pt_s.mean(), 'mean_full': pf_s.mean()
            })
    size_df = pd.DataFrame(size_rows)

    bal_rows = []
    for b in ['Balanced', 'Unbalanced']:
        sub = merged[merged['balance'] == b]
        if len(sub) > 0:
            pt_b, pf_b = sub['route_time_p'], sub['route_time_f']
            bal_rows.append({
                'balance': b, 'n': len(sub),
                'partial_better': (pt_b < pf_b).sum(), 'full_better': (pf_b < pt_b).sum(),
                'avg_improvement': ((pf_b - pt_b) / pf_b * 100).mean(),
                'mean_partial': pt_b.mean(), 'mean_full': pf_b.mean()
            })
    balance_df = pd.DataFrame(bal_rows)

    return size_df, balance_df


def build_appendix(base, strat_data):
    """Full table: instance, route_time, computation_time, labels_generated, labels_dominated, charging_sync for each strategy."""
    instances = sorted(base["instance_clean"].dropna().unique(), key=instance_sort_key)
    all_strats = STRATEGIES + (['Greedy_Diesel_LB'] if 'Greedy_Diesel_LB' in base['strategy'].values else [])
    has_charging = 'num_charges' in base.columns
    charging_cols = ['num_charges', 'num_synchronized', 'num_unsynchronized', 'num_sync_with_break', 'num_sync_with_rest'] if has_charging else []
    rows = []
    for inst in instances:
        row = {'instance': inst}
        for strat in all_strats:
            sd = strat_data.get(strat)
            if sd is not None and not sd.empty:
                s = sd[sd['instance_clean'] == inst]
            else:
                s = base[(base['strategy'] == strat) & (base['instance_clean'] == inst)]
            if not s.empty:
                s = s.iloc[0]
                row[f'{strat}_route_time_hrs'] = round(s.get('route_time', np.nan), 2)
                ct = s.get('comp_time_sec', s.get('computation_time_sec', s.get('computation_time', np.nan)))
                row[f'{strat}_computation_sec'] = round(float(ct), 4) if pd.notna(ct) else np.nan
                lg = s.get('num_labels_generated')
                row[f'{strat}_labels_generated'] = int(lg) if pd.notna(lg) else np.nan
                ld = s.get('num_labels_dominated')
                row[f'{strat}_labels_dominated'] = int(ld) if pd.notna(ld) else np.nan
                for ccol in charging_cols:
                    if ccol in s.index:
                        v = s[ccol]
                        row[f'{strat}_{ccol}'] = int(v) if pd.notna(v) else np.nan
            else:
                row[f'{strat}_route_time_hrs'] = row[f'{strat}_computation_sec'] = row[f'{strat}_labels_generated'] = row[f'{strat}_labels_dominated'] = np.nan
                for ccol in charging_cols:
                    row[f'{strat}_{ccol}'] = np.nan
        rows.append(row)
    return pd.DataFrame(rows)


# --- FIGURES ---

def _per_instance_comparisons_figsize(n_instances: int) -> tuple[float, float]:
    """Figure 2b: narrower than the old 3×2 right column, taller for readable x-labels."""
    w = float(max(7.2, min(12.8, 3.8 + n_instances * 0.12)))
    h = 13.2
    return w, h


def _set_per_instance_xticks(
    ax,
    merged: pd.DataFrame,
    *,
    rotation: float = 55,
    id_fontsize: float = 6,
    name_fontsize: float = 7,
) -> None:
    """X-axis: mnemonic id if column id is present, else full instance name."""
    n = len(merged)
    ax.set_xticks(np.arange(n))
    if "id" in merged.columns:
        labels = [str(i) for i in merged["id"].values]
        ax.set_xticklabels(labels, rotation=rotation, ha="right", fontsize=id_fontsize)
        #ax.set_xlabel("Instance code (see table_00_instance_id_map.csv)")
    else:
        ax.set_xticklabels(
            merged["instance_clean"].astype(str), rotation=62, ha="right", fontsize=name_fontsize
        )
        ax.set_xlabel("Instance (name matches bar order)", fontsize=name_fontsize)


def _style_fig2b_axis(ax) -> None:
    """Larger type for per-instance comparison panels (figure 2b)."""
    ax.tick_params(axis="y", labelsize=10)
    ax.title.set_fontsize(11)
    ax.yaxis.label.set_fontsize(10)
    leg = ax.get_legend()
    if leg is not None:
        for t in leg.get_texts():
            t.set_fontsize(9)


def fig_base_scenario_grouped_bar(base, strat_data, fig_dir, id_map_df: pd.DataFrame | None = None):
    """Three separate figures: (1) Route time per instance, (2) Avg route time by group, (3) Avg computation time by group.
    Same format/style for all."""
    instances = instances_from_strategies(strat_data)
    base_ev = base.loc[base_scenario_ev_mask(base)]
    base_group = pd.concat(
        [base_ev, base.loc[base["strategy"] == "Partial_Diesel_LB"]],
        ignore_index=True,
    )
    if len(instances) == 0:
        return
    id_by_inst: dict[str, str] = {}
    if id_map_df is not None and not id_map_df.empty:
        id_by_inst = dict(zip(id_map_df["instance_clean"].astype(str), id_map_df["id"].astype(str)))

    # Build matrix: instance x strategy
    data = {s: [] for s in STRATEGIES}
    for inst in instances:
        for s in STRATEGIES:
            sd = strat_data.get(s)
            if sd is not None and not sd.empty:
                r = sd[sd['instance_clean'] == inst]
                data[s].append(r['route_time'].iloc[0] if len(r) > 0 else np.nan)
            else:
                data[s].append(np.nan)

    # Group boundaries for dashed lines (between short|med, med|long)
    group_sizes = []
    for sz in ['short', 'medium', 'large']:
        n = sum(1 for i in instances if get_problem_size(i) == sz)
        group_sizes.append(n)
    sep_idx = [group_sizes[0] - 0.5, group_sizes[0] + group_sizes[1] - 0.5]  # after last short, after last medium

    x = np.arange(len(instances))
    w = 0.2
    colors = {'Full': '#5B8FA3', 'Partial': '#E07B4D', 'Greedy': '#4A7C59', 'Partial_Diesel_LB': '#C9A227'}
    STRAT_NO_GREEDY = [s for s in STRATEGIES if s != 'Greedy']
    groups = ['short', 'medium', 'large']
    group_labels = ['Short', 'Medium', 'Long']

    comp_col = 'comp_time_sec' if 'comp_time_sec' in base.columns else 'computation_time_sec'
    if comp_col not in base.columns:
        comp_col = 'computation_time'

    # --- Figure 1: Route time per instance ---
    fig1 = plt.figure(figsize=(max(14, len(instances) * 0.35), 5))
    ax_main = fig1.add_subplot(111)
    for i, s in enumerate(STRATEGIES):
        vals = data[s]
        offset = (i - 1.5) * w
        ax_main.bar(x + offset, vals, w, label=STRATEGY_LABELS.get(s, s), color=colors.get(s, 'gray'), alpha=0.85)
    for xi in sep_idx:
        ax_main.axvline(xi, color='black', linestyle='--', linewidth=1, alpha=0.7)
    y_max = max([v for vals in data.values() for v in vals if pd.notna(v)], default=100) * 1.15
    cum = 0
    for n, lbl in zip(group_sizes, ['Short', 'Medium', 'Long']):
        x_center = cum + (n - 1) / 2 if n > 0 else cum
        ax_main.text(x_center, y_max * 0.98, lbl, ha='center', va='top', fontsize=11, fontweight='bold')
        cum += n
    ax_main.set_xticks(x)
    if id_by_inst:
        #ax_main.set_xlabel("Instance code (see table_00_instance_id_map.csv)")
        ax_main.set_xticklabels([id_by_inst[i] for i in instances], rotation=55, ha="right", fontsize=7)
    else:
        ax_main.set_xlabel("Instance")
        ax_main.set_xticklabels(instances, rotation=90, ha="right")
    ax_main.set_ylabel("Total route time (hours)")
    ax_main.set_title("Base-Scenario: Total Route Time Comparison per Instance")
    leg = ax_main.legend(loc='upper right', frameon=True, fancybox=False, edgecolor='black', framealpha=1)
    leg.get_frame().set_linewidth(0.8)
    ax_main.set_ylim(0, y_max)
    ax_main.grid(axis='y', alpha=0.3)
    ax_main.set_xlim(-0.6, len(instances) - 0.7)
    plt.tight_layout()
    plt.savefig(fig_dir / '01_base_scenario_route_time_per_instance.png', dpi=150, bbox_inches='tight')
    plt.close()

    # --- Figure 2: Avg route time by group ---
    fig2, ax_rt = plt.subplots(figsize=(6, 4))
    x_grp = np.arange(len(groups))
    w_bar = 0.2
    all_vals_rt = []
    for i, s in enumerate(STRATEGIES):
        vals = []
        for g in groups:
            inst_in_g = [inst for inst in instances if get_problem_size(inst) == g]
            rows = base_group[
                (base_group["instance_clean"].isin(inst_in_g)) & (base_group["strategy"] == s)
            ]
            v = rows["route_time"].mean() if not rows.empty else np.nan
            vals.append(v)
            all_vals_rt.append(v)
        offset = (i - 1.5) * w_bar
        bars = ax_rt.bar(x_grp + offset, vals, w_bar, label=STRATEGY_LABELS.get(s, s), color=colors.get(s, 'gray'), alpha=0.85)
        max_v = max((v for v in vals if pd.notna(v)), default=0)
        for b, v in zip(bars, vals):
            if pd.notna(v) and v > 0:
                ax_rt.text(b.get_x() + b.get_width()/2, b.get_height() + max_v * 0.02, f'{v:.1f}', ha='center', va='bottom', fontsize=8)
    ax_rt.set_xticks(x_grp)
    ax_rt.set_xticklabels(group_labels)
    ax_rt.set_ylabel('Mean route time (hours)')
    ax_rt.set_title('Avg route time by group')
    ax_rt.legend(fontsize=8)
    valid = [v for v in all_vals_rt if pd.notna(v) and v > 0]
    if valid:
        ax_rt.set_ylim(0, max(valid) * 1.2)
    ax_rt.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig(fig_dir / '01b_avg_route_time_by_group.png', dpi=150, bbox_inches='tight')
    plt.close()

    # --- Figure 3: Avg computation time by group ---
    fig3, ax_ct = plt.subplots(figsize=(6, 4))
    all_vals_ct = []
    for i, s in enumerate(STRAT_NO_GREEDY):
        vals = []
        for g in groups:
            inst_in_g = [inst for inst in instances if get_problem_size(inst) == g]
            rows = base_group[
                (base_group["instance_clean"].isin(inst_in_g)) & (base_group["strategy"] == s)
            ]
            v = rows[comp_col].mean() if not rows.empty and comp_col in rows.columns else np.nan
            vals.append(v)
            all_vals_ct.append(v)
        offset = (i - (len(STRAT_NO_GREEDY) - 1) / 2) * w_bar
        bars = ax_ct.bar(x_grp + offset, vals, w_bar, label=STRATEGY_LABELS.get(s, s), color=colors.get(s, 'gray'), alpha=0.85)
        max_v = max((v for v in vals if pd.notna(v)), default=0)
        for b, v in zip(bars, vals):
            if pd.notna(v) and v > 0:
                lbl = f'{v:.0f}s' if v >= 1 else f'{v*1000:.0f}ms'
                ax_ct.text(b.get_x() + b.get_width()/2, b.get_height() + max_v * 0.02, lbl, ha='center', va='bottom', fontsize=8)
    ax_ct.set_xticks(x_grp)
    ax_ct.set_xticklabels(group_labels)
    ax_ct.set_ylabel('Mean computation time (sec)')
    ax_ct.set_title('Avg computation time by group (excl. Greedy)')
    ax_ct.legend(fontsize=8)
    valid = [v for v in all_vals_ct if pd.notna(v) and v > 0]
    if valid:
        ax_ct.set_ylim(0, max(valid) * 1.2)
    ax_ct.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig(fig_dir / '01c_avg_computation_time_by_group.png', dpi=150, bbox_inches='tight')
    plt.close()


def fig_combined_comparisons(comp, fig_dir):
    """Two figures (2a / 2b): aggregated mean bars vs per-instance bars (same three comparison rows)."""
    has_any = any(k in comp for k in ['full_vs_partial', 'partial_vs_greedy', 'partial_vs_diesel'])
    if not has_any:
        return

    # Same color palette as 01_base_scenario_route_time_per_instance.png
    colors = {'Full': '#5B8FA3', 'Partial': '#E07B4D', 'Greedy': '#4A7C59', 'Partial_Diesel_LB': '#C9A227'}
    color_improvement = '#4A7C59'   # Greedy green
    color_ev_gap = '#C9A227'        # Diesel gold

    n_inst = max(
        (len(comp[k]['merged']) for k in ('full_vs_partial', 'partial_vs_greedy', 'partial_vs_diesel') if k in comp),
        default=10,
    )
    gs_kw = {'hspace': 0.42}
    gs_kw_b = {'hspace': 0.32}
    fig_a, ax_a = plt.subplots(3, 1, figsize=(6, 10.5), gridspec_kw=gs_kw)
    w2b, h2b = _per_instance_comparisons_figsize(n_inst)
    fig_b, ax_b = plt.subplots(3, 1, figsize=(w2b, h2b), gridspec_kw=gs_kw_b)

    # Row 0: Full vs Partial
    if 'full_vs_partial' in comp:
        fp = comp['full_vs_partial']
        m = fp['merged']
        pt, pf = m['route_time_p'], m['route_time_f']
        ax = ax_a[0]
        bars = ax.bar(['Full', 'Partial'], [pf.mean(), pt.mean()], color=[colors['Full'], colors['Partial']], alpha=0.85)
        for bar, val in zip(bars, [pf.mean(), pt.mean()]):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5, f'{val:.1f}h', ha='center', va='bottom', fontsize=9)
        ax.set_ylabel('Mean route time (hours)')
        ax.set_title('Mean Route Time: Full vs Partial')
        ax = ax_b[0]
        diff_pct = (pf - pt) / pf * 100
        x = np.arange(len(m))
        ax.bar(x, diff_pct, color=color_improvement, alpha=0.85)
        ax.axhline(diff_pct.mean(), color='red', linestyle='--', linewidth=1.5, label=f'Avg: {diff_pct.mean():.1f}%')
        ax.axhline(0, color='black', linewidth=0.5)
        ax.set_ylabel('Improvement % (Partial vs Full)')
        ax.set_title('Per-instance: Partial improvement over Full')
        ax.legend()
        _set_per_instance_xticks(ax, m, rotation=48, id_fontsize=8.5, name_fontsize=9)
        _style_fig2b_axis(ax)
    else:
        ax_a[0].axis('off')
        ax_b[0].axis('off')

    # Row 1: Partial vs Greedy
    if 'partial_vs_greedy' in comp:
        pg = comp['partial_vs_greedy']
        m = pg['merged']
        pt, pg_vals = m['route_time_p'], m['route_time_g']
        ax = ax_a[1]
        bars = ax.bar(['Greedy', 'Partial'], [pg_vals.mean(), pt.mean()], color=[colors['Greedy'], colors['Partial']], alpha=0.85)
        for bar, val in zip(bars, [pg_vals.mean(), pt.mean()]):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, f'{val:.1f}h', ha='center', va='bottom', fontsize=9)
        ax.set_ylabel('Mean route time (hours)')
        ax.set_title('Mean Route Time: Partial vs Greedy')
        ax = ax_b[1]
        imp = (pg_vals - pt) / pg_vals * 100
        x = np.arange(len(m))
        ax.bar(x, imp, color=color_improvement, alpha=0.85)
        ax.axhline(imp.mean(), color='red', linestyle='--', linewidth=1.5, label=f'Avg: {imp.mean():.1f}%')
        ax.axhline(0, color='black', linewidth=0.5)
        ax.set_ylabel('Improvement % (Partial vs Greedy)')
        ax.set_title('Per-instance: Partial improvement over Greedy')
        ax.legend()
        _set_per_instance_xticks(ax, m, rotation=48, id_fontsize=8.5, name_fontsize=9)
        _style_fig2b_axis(ax)
    else:
        ax_a[1].axis('off')
        ax_b[1].axis('off')

    # Row 2: Partial vs Diesel LB
    if 'partial_vs_diesel' in comp:
        m = comp['partial_vs_diesel']['merged']
        pt, pd_ = m['route_time_p'], m['route_time_d']
        ax = ax_a[2]
        bars = ax.bar(
            ['Diesel proxy', 'Partial (EV)'],
            [pd_.mean(), pt.mean()],
            color=[colors['Partial_Diesel_LB'], colors['Partial']],
            alpha=0.85,
        )
        for bar, val in zip(bars, [pd_.mean(), pt.mean()]):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3, f'{val:.1f}h', ha='center', va='bottom', fontsize=9)
        ax.set_ylabel('Mean route time (hours)')
        ax.set_title('Mean route time: Partial (EV) vs diesel proxy (high-battery partial)')
        ax = ax_b[2]
        gap = (pt - pd_) / pd_ * 100
        x = np.arange(len(m))
        ax.bar(x, gap, color=color_ev_gap, alpha=0.85)
        ax.axhline(gap.mean(), color='red', linestyle='--', linewidth=1.5, label=f'Avg EV gap: {gap.mean():.1f}%')
        ax.axhline(0, color='black', linewidth=0.5)
        ax.set_ylabel('EV time gap % vs diesel proxy')
        ax.set_title('Per-instance: EV vs diesel proxy (positive = EV slower)')
        ax.legend()
        _set_per_instance_xticks(ax, m, rotation=48, id_fontsize=8.5, name_fontsize=9)
        _style_fig2b_axis(ax)
    else:
        ax_a[2].axis('off')
        ax_b[2].axis('off')

    for fig in (fig_a, fig_b):
        fig.tight_layout()
    fig_a.savefig(fig_dir / '02a_comparisons_mean_route_time.png', dpi=150, bbox_inches='tight')
    fig_b.savefig(fig_dir / '02b_comparisons_per_instance.png', dpi=150, bbox_inches='tight')
    plt.close(fig_a)
    plt.close(fig_b)
    fig_comparisons_per_instance_boxplots(comp, fig_dir)


def fig_comparisons_per_instance_boxplots(comp, fig_dir):
    """Side-by-side box plots of the same per-instance % metrics as figure 2b."""
    color_improvement = '#4A7C59'   # Greedy green (matches 2b)
    color_ev_gap = '#C9A227'        # Diesel gold (matches 2b)

    panels: list[dict] = []
    if 'full_vs_partial' in comp:
        m = comp['full_vs_partial']['merged']
        pt, pf = m['route_time_p'], m['route_time_f']
        panels.append({
            'data': (pf - pt) / pf * 100,
            'color': color_improvement,
            'title': 'Partial improvement over Full',
            'ylabel': 'Improvement % (Partial vs Full)',
            'avg_label': 'Avg',
        })
    if 'partial_vs_greedy' in comp:
        m = comp['partial_vs_greedy']['merged']
        pt, pg_vals = m['route_time_p'], m['route_time_g']
        panels.append({
            'data': (pg_vals - pt) / pg_vals * 100,
            'color': color_improvement,
            'title': 'Partial improvement over Greedy',
            'ylabel': 'Improvement % (Partial vs Greedy)',
            'avg_label': 'Avg',
        })
    if 'partial_vs_diesel' in comp:
        m = comp['partial_vs_diesel']['merged']
        pt, pd_ = m['route_time_p'], m['route_time_d']
        panels.append({
            'data': (pt - pd_) / pd_ * 100,
            'color': color_ev_gap,
            'title': 'EV vs diesel proxy (positive = EV slower)',
            'ylabel': 'EV time gap % vs diesel proxy',
            'avg_label': 'Avg EV gap',
        })
    if not panels:
        return

    n_panels = len(panels)
    fig, axes = plt.subplots(1, n_panels, figsize=(3.6 * n_panels, 4.8), squeeze=False)
    axes = axes.flatten()

    for ax, panel in zip(axes, panels):
        vals = panel['data'].to_numpy(dtype=float)
        bp = ax.boxplot(
            [vals],
            widths=0.45,
            patch_artist=True,
            showfliers=True,
            medianprops={'color': 'black', 'linewidth': 1.2},
            whiskerprops={'color': 'black', 'linewidth': 0.8},
            capprops={'color': 'black', 'linewidth': 0.8},
            boxprops={'linewidth': 0.8, 'edgecolor': 'black'},
            flierprops={'marker': 'o', 'markersize': 4, 'markerfacecolor': panel['color'], 'alpha': 0.6},
        )
        bp['boxes'][0].set_facecolor(panel['color'])
        bp['boxes'][0].set_alpha(0.85)

        mean_v = float(np.mean(vals))
        ax.axhline(
            mean_v,
            color='red',
            linestyle='--',
            linewidth=1.5,
            label=f"{panel['avg_label']}: {mean_v:.1f}%",
        )
        ax.axhline(0, color='black', linewidth=0.5)
        ax.set_xticks([1])
        ax.set_xticklabels([f"$n={len(vals)}$"], fontsize=9)
        ax.set_ylabel(panel['ylabel'])
        ax.set_title(panel['title'])
        ax.legend(loc='upper right', fontsize=9)
        _style_fig2b_axis(ax)

    fig.tight_layout()
    fig.savefig(fig_dir / '02c_comparisons_per_instance_boxplots.png', dpi=150, bbox_inches='tight')
    plt.close(fig)


def fig_problem_size(size_df, fig_dir):
    """Paper-ready title/label wording for partial vs full by problem size."""
    if size_df.empty:
        return
    colors = {'Full': '#5B8FA3', 'Partial': '#6B4E8E'}  # Partial: slight dark purple
    fig, ax = plt.subplots(figsize=(6, 4))
    x = np.arange(len(size_df))
    w = 0.35
    bars1 = ax.bar(x - w/2, size_df['mean_full'], w, label='Full', color=colors['Full'], alpha=0.85)
    bars2 = ax.bar(x + w/2, size_df['mean_partial'], w, label='Partial', color=colors['Partial'], alpha=0.85)
    for bar1, bar2 in zip(bars1, bars2):
        ax.text(bar1.get_x() + bar1.get_width()/2, bar1.get_height() + 0.5, f'{bar1.get_height():.1f}', ha='center', va='bottom', fontsize=8)
        ax.text(bar2.get_x() + bar2.get_width()/2, bar2.get_height() + 0.5, f'{bar2.get_height():.1f}', ha='center', va='bottom', fontsize=8)
    # Improvement % and hours in top-left box
    box_lines = ['Improvement:']
    for _, row in size_df.iterrows():
        imp_hrs = row['mean_full'] - row['mean_partial']
        box_lines.append(f"{row['size'].capitalize()}: {row['avg_improvement']:.1f}% ({imp_hrs:.1f}h)")
    box_text = '\n'.join(box_lines)
    ax.text(0.02, 0.98, box_text, transform=ax.transAxes, fontsize=9, verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='white', edgecolor='black', alpha=0.9))
    ax.set_xticks(x)
    ax.set_xticklabels(size_df['size'].str.capitalize())
    ax.set_xlabel('Problem size')
    ax.set_ylabel('Mean route time (hours)')
    ax.set_title('Mean Route Time by Problem Size (Partial vs Full)')
    ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1))
    plt.tight_layout()
    plt.savefig(fig_dir / '05_problem_size_partial_vs_full.png', dpi=150, bbox_inches='tight')
    plt.close()


def fig_balance(balance_df, fig_dir):
    """Paper-ready title/label wording for partial vs full by balance."""
    if balance_df.empty:
        return
    colors = {'Full': '#5B8FA3', 'Partial': '#6B4E8E'}  # Partial: slight dark purple
    fig, ax = plt.subplots(figsize=(6, 4))
    x = np.arange(len(balance_df))
    w = 0.35
    bars1 = ax.bar(x - w/2, balance_df['mean_full'], w, label='Full', color=colors['Full'], alpha=0.85)
    bars2 = ax.bar(x + w/2, balance_df['mean_partial'], w, label='Partial', color=colors['Partial'], alpha=0.85)
    for bar1, bar2 in zip(bars1, bars2):
        ax.text(bar1.get_x() + bar1.get_width()/2, bar1.get_height() + 0.5, f'{bar1.get_height():.1f}', ha='center', va='bottom', fontsize=8)
        ax.text(bar2.get_x() + bar2.get_width()/2, bar2.get_height() + 0.5, f'{bar2.get_height():.1f}', ha='center', va='bottom', fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(balance_df['balance'])
    ax.set_xlabel('Balance')
    ax.set_ylabel('Mean route time (hours)')
    ax.set_title('Mean Route Time by Balance (Partial vs Full)')
    leg = ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1))
    # Improvement box outside, below legend
    box_lines = ['Improvement:']
    for _, row in balance_df.iterrows():
        imp_hrs = row['mean_full'] - row['mean_partial']
        box_lines.append(f"{row['balance']}: {row['avg_improvement']:.1f}% ({imp_hrs:.1f}h)")
    fig.text(0.98, 0.45, '\n'.join(box_lines), fontsize=9, verticalalignment='top', horizontalalignment='right',
             bbox=dict(boxstyle='round', facecolor='white', edgecolor='black', alpha=0.9), transform=fig.transFigure)
    plt.tight_layout()
    plt.savefig(fig_dir / '06_balance_partial_vs_full.png', dpi=150, bbox_inches='tight')
    plt.close()


def fig_computation_time(base, fig_dir):
    """Computation time by strategy (Full, Partial, Diesel LB - excludes Greedy)."""
    comp_col = 'comp_time_sec' if 'comp_time_sec' in base.columns else 'computation_time_sec' if 'computation_time_sec' in base.columns else 'computation_time'
    if comp_col not in base.columns:
        return
    mask_ct = base_scenario_ev_mask(base) | (base["strategy"].astype(str) == "Partial_Diesel_LB")
    strat_data = base.loc[mask_ct].groupby("strategy")[comp_col].agg(["mean", "median"]).reset_index()
    strat_no_greedy = [s for s in STRATEGIES if s != 'Greedy']  # Full, Partial, Diesel LB only
    strat_data = strat_data[strat_data['strategy'].isin(strat_no_greedy)]
    order = {s: i for i, s in enumerate(strat_no_greedy)}
    strat_data = strat_data.sort_values('strategy', key=lambda c: c.map(order))
    if strat_data.empty:
        return
    fig, ax = plt.subplots(figsize=(6, 4))
    x = np.arange(len(strat_data))
    labels = [STRATEGY_LABELS.get(s, s) for s in strat_data['strategy']]
    palette = ['#5B8FA3', '#6B4E8E', '#C9A227']  # Full, Partial, Diesel LB (excl. Greedy)
    bars = ax.bar(x, strat_data['mean'], color=palette[:len(strat_data)], alpha=0.85)
    for bar, val in zip(bars, strat_data['mean']):
        lbl = f'{val:.2f}s' if val >= 0.01 else f'{val*1000:.1f}ms'
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(strat_data['mean'])*0.02, lbl, ha='center', va='bottom', fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15)
    ax.set_ylabel('Mean computation time (sec)')
    ax.set_title('Computation Time by Strategy')
    plt.tight_layout()
    plt.savefig(fig_dir / '07_computation_time.png', dpi=150, bbox_inches='tight')
    plt.close()


# --- TABLES ---

def save_tables(
    comp,
    size_df,
    balance_df,
    appendix_df,
    base,
    tbl_dir,
    id_map_df: pd.DataFrame | None = None,
    strat_data: dict | None = None,
):
    if id_map_df is not None and not id_map_df.empty:
        _safe_dataframe_to_csv(id_map_df, tbl_dir / "table_00_instance_id_map.csv", index=False)

    # Base-case benchmark table (table_01): mean route times + partial advantage as
    # Average: mean % and mean delta-min. Min/max: instances with smallest/largest delta in minutes
    # (then show that instance's %); keeps min_min <= mean_min <= max_min for the minute values.
    rows = []
    if 'full_vs_partial' in comp:
        fp = comp['full_vs_partial']
        rows.extend([
            {'Comparison': 'Full vs Partial', 'Metric': 'Mean Partial (hrs)', 'Value': f"{fp['mean_partial']:.2f}"},
            {'Comparison': 'Full vs Partial', 'Metric': 'Mean Full (hrs)', 'Value': f"{fp['mean_full']:.2f}"},
            {
                'Comparison': 'Full vs Partial',
                'Metric': 'Partial advantage average',
                'Value': fp['partial_advantage_avg'],
            },
            {
                'Comparison': 'Full vs Partial',
                'Metric': 'Partial advantage minimum',
                'Value': fp['partial_advantage_min'],
            },
            {
                'Comparison': 'Full vs Partial',
                'Metric': 'Partial advantage maximum',
                'Value': fp['partial_advantage_max'],
            },
        ])
    if 'partial_vs_greedy' in comp:
        pg = comp['partial_vs_greedy']
        rows.extend([
            {'Comparison': 'Partial vs Greedy', 'Metric': 'Mean Partial (hrs)', 'Value': f"{pg['mean_partial']:.2f}"},
            {'Comparison': 'Partial vs Greedy', 'Metric': 'Mean Greedy (hrs)', 'Value': f"{pg['mean_greedy']:.2f}"},
            {
                'Comparison': 'Partial vs Greedy',
                'Metric': 'Partial advantage average',
                'Value': pg['partial_advantage_avg'],
            },
            {
                'Comparison': 'Partial vs Greedy',
                'Metric': 'Partial advantage minimum',
                'Value': pg['partial_advantage_min'],
            },
            {
                'Comparison': 'Partial vs Greedy',
                'Metric': 'Partial advantage maximum',
                'Value': pg['partial_advantage_max'],
            },
        ])
    if 'partial_vs_diesel' in comp:
        pd_ = comp['partial_vs_diesel']
        rows.extend([
            {'Comparison': 'Partial vs diesel proxy', 'Metric': 'Mean Partial (hrs)', 'Value': f"{pd_['mean_partial']:.2f}"},
            {'Comparison': 'Partial vs diesel proxy', 'Metric': 'Mean diesel proxy (hrs)', 'Value': f"{pd_['mean_diesel']:.2f}"},
            {
                'Comparison': 'Partial vs diesel proxy',
                'Metric': 'Partial advantage average',
                'Value': pd_['partial_advantage_avg'],
            },
            {
                'Comparison': 'Partial vs diesel proxy',
                'Metric': 'Partial advantage minimum',
                'Value': pd_['partial_advantage_min'],
            },
            {
                'Comparison': 'Partial vs diesel proxy',
                'Metric': 'Partial advantage maximum',
                'Value': pd_['partial_advantage_max'],
            },
        ])
    if rows:
        _safe_dataframe_to_csv(
            pd.DataFrame(rows), tbl_dir / "table_01_combined_comparisons.csv", index=False
        )

    if 'full_vs_partial' in comp:
        m = comp['full_vs_partial']['merged'].copy()
        if 'id' not in m.columns and id_map_df is not None and not id_map_df.empty:
            m = m.merge(id_map_df, on='instance_clean', how='left')
        m['improvement_pct_partial_vs_full'] = (m['route_time_f'] - m['route_time_p']) / m['route_time_f'] * 100
        m = m.rename(
            columns={'route_time_p': 'partial_route_time_h', 'route_time_f': 'full_route_time_h'}
        )
        cols = ['id', 'instance_clean', 'partial_route_time_h', 'full_route_time_h', 'improvement_pct_partial_vs_full']
        _safe_dataframe_to_csv(
            m[[c for c in cols if c in m.columns]],
            tbl_dir / "table_02_per_instance_partial_vs_full.csv",
            index=False,
        )

    if 'partial_vs_diesel' in comp:
        m = comp['partial_vs_diesel']['merged'].copy()
        if 'id' not in m.columns and id_map_df is not None and not id_map_df.empty:
            m = m.merge(id_map_df, on='instance_clean', how='left')
        m['ev_gap_pct_vs_diesel_proxy'] = (m['route_time_p'] - m['route_time_d']) / m['route_time_d'] * 100
        m = m.rename(
            columns={'route_time_p': 'partial_ev_route_time_h', 'route_time_d': 'diesel_proxy_route_time_h'}
        )
        cols = [
            'id',
            'instance_clean',
            'partial_ev_route_time_h',
            'diesel_proxy_route_time_h',
            'ev_gap_pct_vs_diesel_proxy',
        ]
        _safe_dataframe_to_csv(
            m[[c for c in cols if c in m.columns]],
            tbl_dir / "table_03_per_instance_partial_vs_diesel_proxy.csv",
            index=False,
        )

    if not size_df.empty:
        tbl = size_df.copy()
        if 'avg_improvement' in tbl.columns:
            tbl = tbl.rename(columns={'avg_improvement': 'Improvement %'})
        _safe_dataframe_to_csv(tbl, tbl_dir / "table_04_problem_size.csv", index=False)
    if not balance_df.empty:
        _safe_dataframe_to_csv(balance_df, tbl_dir / "table_05_balance.csv", index=False)
    if not appendix_df.empty:
        apx = appendix_df.copy()
        if id_map_df is not None and not id_map_df.empty:
            apx = apx.merge(id_map_df, left_on='instance', right_on='instance_clean', how='left')
            apx = apx.drop(columns=['instance_clean'])
            front = ['id', 'instance']
            rest = [c for c in apx.columns if c not in front]
            apx = apx[[c for c in front + rest if c in apx.columns]]
        _safe_dataframe_to_csv(apx, tbl_dir / "table_appendix_full_results.csv", index=False)

    if strat_data is not None:
        summary_df = build_route_activity_summary(strat_data, id_map_df)
        if not summary_df.empty:
            _safe_dataframe_to_csv(
                summary_df, tbl_dir / "table_summary_route_times_and_activity.csv", index=False
            )
            write_route_activity_summary_markdown(
                summary_df, tbl_dir / "table_summary_route_times_and_activity.md"
            )

    if strat_data is not None:
        save_thesis_diagnostic_analyst_tables(strat_data, tbl_dir, id_map_df)

    # Charging sync per row (if columns exist)
    charging_cols = ['num_charges', 'num_synchronized', 'num_unsynchronized',
                     'num_sync_with_break', 'num_sync_with_rest',
                     'num_unsynchronized_breaks', 'num_unsynchronized_rests']
    if all(c in base.columns for c in charging_cols):
        key_cols = ['instance_clean', 'strategy', 'route_time'] + charging_cols
        key_cols = [c for c in key_cols if c in base.columns]
        ch_mask = base_scenario_ev_mask(base) | (base["strategy"].astype(str) == "Partial_Diesel_LB")
        ch = base.loc[ch_mask, key_cols].copy()
        if id_map_df is not None and not id_map_df.empty:
            ch = ch.merge(id_map_df, on='instance_clean', how='left')
            rest = [c for c in ch.columns if c not in ('id', 'instance_clean')]
            ch = ch[['id', 'instance_clean'] + rest]
        _safe_dataframe_to_csv(ch, tbl_dir / "table_charging_sync.csv", index=False)


# --- REPORT ---

def write_report(comp, size_df, balance_df, report_path):
    lines = []
    lines.append("# Base-Scenario Post-Analysis: EV Routing Strategies")
    lines.append("")
    lines.append("Solution time and optimality: Full vs Partial vs Greedy vs Diesel LB.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 1. Executive Summary")
    lines.append("")

    if 'full_vs_partial' in comp:
        fp = comp['full_vs_partial']
        lines.append(f"- **Full vs Partial:** Partial better in {fp['partial_better']}/{fp['n']} instances, avg improvement {fp['avg_improvement']:.2f}%")
    if 'partial_vs_greedy' in comp:
        pg = comp['partial_vs_greedy']
        lines.append(f"- **Partial vs Greedy:** Partial better in {pg['partial_better']}/{pg['n']} instances, avg improvement {pg['avg_improvement']:.2f}%")
    if 'partial_vs_diesel' in comp:
        pd_ = comp['partial_vs_diesel']
        lines.append(
            f"- **Partial (EV) vs diesel proxy:** Mean EV {pd_['mean_partial']:.2f}h vs proxy {pd_['mean_diesel']:.2f}h; "
            f"avg EV time gap {pd_['gap_pct']:.2f}% (proxy faster in {pd_['diesel_faster']}/{pd_['n']} instances)"
        )
    lines.append("")
    lines.append("**Figures:** `analysis_output_baseScenario/figures/`")
    lines.append("**Tables:** `analysis_output_baseScenario/tables/`")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## 2. Per-instance summary (route times + activity / synchronization)")
    lines.append("")
    lines.append(f"**EV labeling configuration (Full & Partial):** {route_summary_config_caption()}")
    lines.append("")
    lines.append(
        "- **`table_summary_route_times_and_activity.csv`:** one row per instance; columns "
        "`full_*`, `partial_*`, `greedy_*`, `diesel_proxy_*` (route hours, CS stops, breaks, rests, "
        "charge counts, sync events, % charging synchronized, timeline sync splits where present)."
    )
    lines.append("- **`table_summary_route_times_and_activity.md`:** short markdown preview (route times) + pointer to CSV.")
    lines.append("")
    lines.append("The appendix table (`table_appendix_full_results.csv`) remains available for computation time and label counts.")
    lines.append("")
    lines.append("### Thesis-style & diagnostic analyst tables (CSV)")
    lines.append("")
    lines.append(
        "- **`table_thesis_full_vs_partial_per_instance.csv`** — matched EV Full vs Partial: route deltas, "
        "sync % / unsync counts / idle minutes, CS stops, breaks, rests, timeline charge counts, SOC text, short interpretation."
    )
    lines.append(
        "- **`table_thesis_full_vs_partial_by_route_class.csv`** — means by Short / Medium / Long."
    )
    lines.append(
        "- **`table_diagnostic_partial_vs_full_extremes.csv`** — top and bottom instances by "
        "`benefit_full_minus_partial_min` (minutes), with key charging/sync columns."
    )
    lines.append(
        "- **`table_diagnostic_near_diesel_wide.csv`** — instances with small EV vs diesel-proxy route gap; wide metric columns."
    )
    lines.append("- **`table_thesis_diagnostic_caption.txt`** — one-line caption for the above.")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## 3. Base-Scenario: Total Route Time per Instance (All Four Strategies)")
    lines.append("")
    lines.append("![Main Chart](analysis_output_baseScenario/figures/01_base_scenario_route_time_per_instance.png)")
    lines.append("")
    lines.append("![Avg Route Time by Group](analysis_output_baseScenario/figures/01b_avg_route_time_by_group.png)")
    lines.append("")
    lines.append("![Avg Computation Time by Group](analysis_output_baseScenario/figures/01c_avg_computation_time_by_group.png)")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## 4. Comparisons: Full vs Partial, Partial vs Greedy, Partial vs Diesel LB")
    lines.append("")
    if any(k in comp for k in ['full_vs_partial', 'partial_vs_greedy', 'partial_vs_diesel']):
        lines.append("**Figure 2a — Mean route time (aggregated)**")
        lines.append("")
        lines.append("![Figure 2a: mean route time comparisons](analysis_output_baseScenario/figures/02a_comparisons_mean_route_time.png)")
        lines.append("")
        lines.append("**Figure 2b — Per-instance comparisons**")
        lines.append("")
        lines.append("![Figure 2b: per-instance comparisons](analysis_output_baseScenario/figures/02b_comparisons_per_instance.png)")
        lines.append("")
        lines.append("**Figure 2c — Per-instance comparisons (box plots)**")
        lines.append("")
        lines.append("![Figure 2c: per-instance comparison box plots](analysis_output_baseScenario/figures/02c_comparisons_per_instance_boxplots.png)")
        lines.append("")
        if 'full_vs_partial' in comp:
            fp = comp['full_vs_partial']
            lines.append("**Full vs Partial:** Mean route time Full {:.2f}h, Partial {:.2f}h; Partial better in {}/{}; Avg improvement {:.2f}%".format(fp['mean_full'], fp['mean_partial'], fp['partial_better'], fp['n'], fp['avg_improvement']))
        if 'partial_vs_greedy' in comp:
            pg = comp['partial_vs_greedy']
            lines.append("**Partial vs Greedy:** Mean route time Partial {:.2f}h, Greedy {:.2f}h; Partial better in {}/{}; Avg improvement {:.2f}%".format(pg['mean_partial'], pg['mean_greedy'], pg['partial_better'], pg['n'], pg['avg_improvement']))
        if 'partial_vs_diesel' in comp:
            pd_ = comp['partial_vs_diesel']
            lines.append(
                "**Partial vs diesel proxy (high-battery partial):** Mean EV {:.2f}h, proxy {:.2f}h; avg EV gap {:.2f}%; "
                "proxy faster in {}/{} instances.".format(
                    pd_['mean_partial'], pd_['mean_diesel'], pd_['gap_pct'], pd_['diesel_faster'], pd_['n']
                )
            )
        lines.append("")
        lines.append(
            "**Tables:** `table_00_instance_id_map.csv` (id ↔ instance name); `table_01_combined_comparisons.csv`; "
            "`table_02_per_instance_partial_vs_full.csv`; `table_03_per_instance_partial_vs_diesel_proxy.csv`"
        )
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## 5. Partial vs Full by Problem Size and Balance")
    lines.append("")
    if not size_df.empty:
        lines.append("![Problem Size](analysis_output_baseScenario/figures/05_problem_size_partial_vs_full.png)")
        lines.append("")
        lines.append("| Size | N | Partial better | Full better | Improvement % | Mean Partial | Mean Full |")
        lines.append("|------|---|----------------|-------------|-----------------|--------------|-----------|")
        for _, r in size_df.iterrows():
            lines.append(f"| {r['size']} | {r['n']} | {r['partial_better']} | {r['full_better']} | {r['avg_improvement']:.1f}% | {r['mean_partial']:.1f}h | {r['mean_full']:.1f}h |")
    if not balance_df.empty:
        lines.append("")
        lines.append("![Balance](analysis_output_baseScenario/figures/06_balance_partial_vs_full.png)")
        lines.append("")
        lines.append("| Balance | N | Partial better | Full better | Avg improvement |")
        lines.append("|---------|---|----------------|-------------|-----------------|")
        for _, r in balance_df.iterrows():
            lines.append(f"| {r['balance']} | {r['n']} | {r['partial_better']} | {r['full_better']} | {r['avg_improvement']:.1f}% |")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## 6. Computation Time by Strategy")
    lines.append("")
    lines.append("![Computation Time](analysis_output_baseScenario/figures/07_computation_time.png)")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## Charging Synchronization")
    lines.append("")
    lines.append("Per test/configuration: num_charges, num_synchronized, num_unsynchronized, num_sync_with_break, num_sync_with_rest, num_unsynchronized_breaks, num_unsynchronized_rests.")
    lines.append("")
    lines.append("**Table:** `analysis_output_baseScenario/tables/table_charging_sync.csv`")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Appendix: Full Results Table")
    lines.append("")
    lines.append("Complete table: instance, route time, computation time, labels generated, labels dominated, charging sync for each strategy.")
    lines.append("")
    lines.append("**Table:** `analysis_output_baseScenario/tables/table_appendix_full_results.csv`")
    lines.append("")

    report_path.write_text("\n".join(lines), encoding='utf-8')
    print(f"Report: {report_path}")


def main():
    print("Loading base scenario data...")
    base = load_base_data()
    if base.empty:
        print("No base scenario data found.")
        return

    print(f"Base: {len(base)} rows, {base['instance_clean'].nunique()} instances")
    vc = base["strategy"].value_counts()
    print("Rows per strategy (all loaded): " + ", ".join(f"{k}={int(v)}" for k, v in vc.items()))
    ev_mask = base_scenario_ev_mask(base)
    n_non_ev = int((~ev_mask).sum())
    if n_non_ev:
        print(
            f"Excluded {n_non_ev} row(s) from EV base-scenario slice (diesel-proxy battery and/or "
            "non-matching labeling parameters); diesel proxy partials kept separately for EV vs diesel charts."
        )
    vc_ev = base.loc[ev_mask, "strategy"].value_counts()
    print(
        "Rows per strategy (EV base slice): "
        + ", ".join(f"{k}={int(v)}" for k, v in vc_ev.items())
    )

    strat_data = build_strat_data(base)
    print(
        "Instances per strategy (deduped): "
        + ", ".join(f"{s}={len(strat_data[s])}" for s in STRATEGIES)
    )
    id_map_df = build_instance_id_map(base, strat_data)
    comp = compute_comparisons(base, strat_data)
    if 'partial_vs_greedy' not in comp:
        print(
            "Partial vs Greedy comparison skipped: need Greedy rows and matching instance_clean "
            "with Partial (see rows per strategy above)."
        )
    comp = attach_instance_ids_to_comparisons(comp, id_map_df)
    size_df, balance_df = by_problem_size_and_balance(base, strat_data)
    appendix_df = build_appendix(base, strat_data)

    print("Creating figures...")
    fig_base_scenario_grouped_bar(base, strat_data, FIG_DIR, id_map_df)
    fig_combined_comparisons(comp, FIG_DIR)
    fig_problem_size(size_df, FIG_DIR)
    fig_balance(balance_df, FIG_DIR)
    fig_computation_time(base, FIG_DIR)
    print(f"Figures: {FIG_DIR}")

    print("Saving tables...")
    save_tables(
        comp, size_df, balance_df, appendix_df, base, TBL_DIR, id_map_df, strat_data=strat_data
    )
    print(f"Tables: {TBL_DIR}")

    print("Writing report...")
    write_report(comp, size_df, balance_df, BASE_DIR / "Post_Analysis_Report_BaseScenario.md")

    print("Done.")


if __name__ == "__main__":
    main()
