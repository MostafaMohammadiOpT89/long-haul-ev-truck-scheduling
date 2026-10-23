"""
Diagnostic markdown tables:
  (1) Partial vs Full â€” top/bottom route-time benefit cases with interpretation.
  (2) Partial EV vs diesel proxy â€” instances with â‰¤15 min route gap; detailed sync/break/rest metrics.

Uses same JSONs and EXCLUDED_INSTANCE_IDS as generate_thesis_full_vs_partial_tables.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from analysis.base_case import EXCLUDED_INSTANCE_IDS, instance_sort_key  # noqa: E402

from analysis.inputs import input_path, ANALYSIS_OUTPUT, record_inputs
BASE_SCENARIO_DIR = input_path("base_unified").parent
PARTIAL_JSON = input_path("base_partial_json")
FULL_JSON = input_path("base_full_json")
OUT_MD = ANALYSIS_OUTPUT / "base_case" / "tables" / "diagnostic_partial_full_and_diesel.md"

DIESEL_BATTERY_KWH = 1.0e9
N_EXTREME = 5  # top / bottom count for Partial vs Full
MAX_NEAR_DIESEL = 6  # cap instances in diesel diagnostic
NEAR_DIESEL_MAX_GAP_MIN = 15.0  # |EV âˆ’ diesel| route time in minutes


def _f(x, default=None):
    if x is None:
        return default
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _i(x, default=0):
    if x is None:
        return default
    try:
        return int(x)
    except (TypeError, ValueError):
        return default


def rows_full_ev(results: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in results:
        if _f(r.get("battery_capacity_kWh"), 0) >= DIESEL_BATTERY_KWH:
            continue
        iid = r.get("instance_id")
        if iid and iid not in out:
            out[str(iid)] = r
    return out


def split_partial_ev_diesel(results: list[dict]) -> tuple[dict[str, dict], dict[str, dict]]:
    ev: dict[str, dict] = {}
    diesel: dict[str, dict] = {}
    for r in results:
        iid = r.get("instance_id")
        if not iid:
            continue
        b = _f(r.get("battery_capacity_kWh"), 0)
        if b >= DIESEL_BATTERY_KWH:
            if iid not in diesel:
                diesel[str(iid)] = r
        else:
            if iid not in ev:
                ev[str(iid)] = r
    return ev, diesel


def metrics(row: dict) -> dict:
    """Numeric fields used in diagnostics."""
    return {
        "route_h": _f(row.get("total_route_time_hours")),
        "sync_pct": _f(row.get("percentage_of_charging_events_synchronized")),
        "unsync_chg": _i(row.get("number_of_unsynchronized_charging_events")),
        "idle_min": _f(row.get("total_idle_charging_time_minutes"), 0.0),
        "sync_ev": _i(row.get("number_of_synchronized_events")),
        "cs_stops": _i(row.get("number_of_cs_stops")),
        "breaks": _i(row.get("number_of_breaks")),
        "rests": _i(row.get("number_of_rests")),
        "rest_sync_chg": _i(row.get("number_of_rest_synchronized_charging_events")),
        "break_full_sync": _i(row.get("number_of_break_fully_synchronized_charging_events")),
        "break_part_sync": _i(row.get("number_of_break_partial_synchronized_charging_events")),
        "break_any_sync": _i(row.get("number_of_break_synchronized_charging_events")),
        "unsync_breaks": _i(row.get("number_of_unsynchronized_breaks")),
        "unsync_rests": _i(row.get("number_of_unsynchronized_rests")),
    }


def diag_partial_vs_full_high(f: dict, p: dict, benefit_min: float) -> str:
    """Why Partial gains a lot vs Full."""
    mf, mp = metrics(f), metrics(p)
    parts = []
    idle_saved = mf["idle_min"] - mp["idle_min"]
    if idle_saved > 5:
        parts.append(f"Idle charging cut by ~{round(idle_saved, 1)} min vs Full.")
    ds = (mp["sync_pct"] or 0) - (mf["sync_pct"] or 0)
    if ds > 5:
        parts.append("Much higher charging-event sync under Partial.")
    du = mf["unsync_chg"] - mp["unsync_chg"]
    if du > 0:
        parts.append(f"{du} fewer unsynchronized charging event(s).")
    if mf["cs_stops"] > mp["cs_stops"]:
        parts.append("Fewer CS stops than Full recharge schedule.")
    if not parts:
        parts.append("Makespan gain with comparable sync counters; check timeline / SOC flexibility.")
    return " ".join(parts)


def diag_partial_vs_full_low(f: dict, p: dict, benefit_min: float) -> str:
    """Why benefit is small or negative; how Full could still help."""
    mf, mp = metrics(f), metrics(p)
    parts = []
    if benefit_min < -0.5:
        parts.append("Full labeling achieves shorter makespan here (mandatory full recharge wins on time).")
    elif abs(benefit_min) < 1.0:
        parts.append("Route times almost identical; both policies land on similar schedules.")
    if (mf["sync_pct"] or 0) >= 99 and (mp["sync_pct"] or 0) >= 99:
        parts.append("Sync rate already at ceiling for both; little room for Partial to differentiate.")
    if mf["unsync_chg"] == 0 and mp["unsync_chg"] == 0:
        parts.append("No unsynchronized charging in either run.")
    if abs(mf["idle_min"] - mp["idle_min"]) < 1:
        parts.append("Idle charging nearly the same.")
    if benefit_min >= -0.5 and benefit_min < 3:
        parts.append(
            "To extract more from Full: focus on instances with high Full idle time or subâ€‘100% sync; "
            "here constraints may dominate."
        )
    if benefit_min < -0.5:
        parts.append(
            "Full remains attractive for pure time minimization on this corridor; Partial trades time for flexibility elsewhere."
        )
    return " ".join(parts)


def md_row_cells(cells: list[str]) -> str:
    return "| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |"


def table_partial_vs_full(top: list[dict], bottom: list[dict]) -> list[str]:
    lines = [
        "## Diagnostic A â€” Partial vs Full (extreme cases)\n",
        f"*Largest **{N_EXTREME}** gains and **{N_EXTREME}** smallest gains in route time (minutes saved by Partial = "
        f"(Full âˆ’ Partial)Ã—60). Excluded instances omitted.*\n",
        "### A.1 Strongest Partial advantage\n",
        md_row_cells(
            [
                "Instance",
                "Î” route (min)",
                "Full sync %",
                "Partial sync %",
                "Î” idle (min)",
                "Why Partial wins (diagnostic)",
                "When Full still matters",
            ]
        ),
        md_row_cells(["---"] * 7),
    ]
    for r in top:
        mf, mp = r["mf"], r["mp"]
        lines.append(
            md_row_cells(
                [
                    f"`{r['iid']}`",
                    f"+{round(r['benefit_min'], 1)}",
                    f"{round(mf['sync_pct'] or 0, 1)}",
                    f"{round(mp['sync_pct'] or 0, 1)}",
                    f"{round(mf['idle_min'] - mp['idle_min'], 1)}",
                    r["diag_high"],
                    "Reference baseline; use if policy requires full recharge only.",
                ]
            )
        )

    lines.append("\n### A.2 Weakest Partial advantage (or Full faster)\n")
    lines.append(
        md_row_cells(
            [
                "Instance",
                "Î” route (min)",
                "Full sync %",
                "Partial sync %",
                "Î” idle (min)",
                "Why little gain / Full ahead",
                "How to leverage Full more",
            ]
        )
    )
    lines.append(md_row_cells(["---"] * 7))
    for r in bottom:
        mf, mp = r["mf"], r["mp"]
        b = r["benefit_min"]
        bstr = f"{round(b, 1)}" if b < 0 else f"+{round(b, 1)}"
        lines.append(
            md_row_cells(
                [
                    f"`{r['iid']}`",
                    bstr,
                    f"{round(mf['sync_pct'] or 0, 1)}",
                    f"{round(mp['sync_pct'] or 0, 1)}",
                    f"{round(mf['idle_min'] - mp['idle_min'], 1)}",
                    r["diag_low"],
                    "Prefer Full when minimizing makespan dominates and sync headroom is low.",
                ]
            )
        )
    return lines


def fmt3(x: float | None) -> str:
    if x is None:
        return "â€”"
    return f"{round(x, 3)}"


def table_partial_vs_diesel(blocks: list[dict]) -> list[str]:
    lines = [
        "\n## Diagnostic B â€” Partial EV vs diesel proxy (nearâ€‘diesel routes)\n",
        f"*Instances with **|route_EV âˆ’ route_diesel|Ã—60 â‰¤ {NEAR_DIESEL_MAX_GAP_MIN:.0f} min**; "
        f"up to **{MAX_NEAR_DIESEL}** tightest matches. Diesel = highâ€‘battery partial row.*\n",
    ]
    if not blocks:
        lines.append("_No instances met the gap threshold._\n")
        return lines

    for b in blocks:
        d, p = b["diesel"], b["partial"]
        md, mp = metrics(d), metrics(p)
        gap = (mp["route_h"] - md["route_h"]) * 60.0
        lines.append(f"### `{b['iid']}` â€” EV excess vs diesel: **{round(gap, 1)} min**\n")
        lines.append("| Metric | Diesel proxy | Partial EV | Î” (EV âˆ’ diesel) |")
        lines.append("| --- | --- | --- | --- |")

        def row(label, vd, vp, *, as_int: bool = False):
            if as_int:
                ds = str(int(vp - vd)) if vd is not None and vp is not None else "â€”"
                return f"| {label} | {vd} | {vp} | {ds} |"
            dv = vp - vd if vd is not None and vp is not None else None
            ds = fmt3(dv) if dv is not None else "â€”"
            return f"| {label} | {fmt3(vd)} | {fmt3(vp)} | {ds} |"

        lines.append(row("Route time (h)", md["route_h"], mp["route_h"]))
        lines.append(row("Sync %", md["sync_pct"], mp["sync_pct"]))
        lines.append(row("Unsync charging events", md["unsync_chg"], mp["unsync_chg"], as_int=True))
        lines.append(row("Idle charging (min)", md["idle_min"], mp["idle_min"]))
        lines.append(row("Synchronized events", md["sync_ev"], mp["sync_ev"], as_int=True))
        lines.append(row("CS stops", md["cs_stops"], mp["cs_stops"], as_int=True))
        lines.append(row("Breaks", md["breaks"], mp["breaks"], as_int=True))
        lines.append(row("Rests", md["rests"], mp["rests"], as_int=True))
        lines.append(row("Restâ€‘sync charging", md["rest_sync_chg"], mp["rest_sync_chg"], as_int=True))
        lines.append(row("Break fullâ€‘sync chg.", md["break_full_sync"], mp["break_full_sync"], as_int=True))
        lines.append(row("Break partialâ€‘sync chg.", md["break_part_sync"], mp["break_part_sync"], as_int=True))
        lines.append(row("Break sync chg. (any)", md["break_any_sync"], mp["break_any_sync"], as_int=True))
        lines.append(row("Unsync breaks", md["unsync_breaks"], mp["unsync_breaks"], as_int=True))
        lines.append(row("Unsync rests", md["unsync_rests"], mp["unsync_rests"], as_int=True))

        # Insight paragraph
        ins = []
        if abs(gap) < 5:
            ins.append("Makespan essentially matches unconstrained energy (diesel proxy).")
        if mp["sync_pct"] and md["sync_pct"] and mp["sync_pct"] >= md["sync_pct"] - 1:
            ins.append("Charging synchronization stays comparable to the proxy despite finite battery.")
        if mp["idle_min"] <= md["idle_min"] + 1:
            ins.append("Idle charging is not inflated vs proxy.")
        if mp["unsync_chg"] == md["unsync_chg"]:
            ins.append("Same unsynchronized charging count as proxy.")
        if not ins:
            ins.append("EV matches diesel time mainly through timing; inspect CS stops and breakâ€‘window use.")
        lines.append("\n*" + " ".join(ins) + "*\n")

    return lines


def main() -> None:
    from common.results import read_records
    partial_data = {"results": read_records(PARTIAL_JSON, "partial_labeling")}
    full_data = {"results": read_records(FULL_JSON, "full_labeling")}

    full_by = rows_full_ev(full_data["results"])
    partial_ev, partial_diesel = split_partial_ev_diesel(partial_data["results"])

    excl = set(EXCLUDED_INSTANCE_IDS)
    common = sorted(set(full_by) & set(partial_ev) - excl, key=instance_sort_key)

    scored: list[dict] = []
    for iid in common:
        f, p = full_by[iid], partial_ev[iid]
        tf = _f(f.get("total_route_time_hours"))
        tp = _f(p.get("total_route_time_hours"))
        if tf is None or tp is None:
            continue
        benefit_min = (tf - tp) * 60.0
        mf, mp = metrics(f), metrics(p)
        scored.append(
            {
                "iid": iid,
                "benefit_min": benefit_min,
                "mf": mf,
                "mp": mp,
                "diag_high": diag_partial_vs_full_high(f, p, benefit_min),
                "diag_low": diag_partial_vs_full_low(f, p, benefit_min),
            }
        )

    scored.sort(key=lambda x: x["benefit_min"], reverse=True)
    top = scored[:N_EXTREME]
    bottom = scored[-N_EXTREME:][::-1]  # smallest benefit first

    # Near-diesel: intersection ev & diesel, exclude
    near: list[dict] = []
    for iid in sorted(set(partial_ev) & set(partial_diesel) - excl, key=instance_sort_key):
        p = partial_ev[iid]
        d = partial_diesel[iid]
        tp = _f(p.get("total_route_time_hours"))
        td = _f(d.get("total_route_time_hours"))
        if tp is None or td is None:
            continue
        gap_min = abs(tp - td) * 60.0
        if gap_min <= NEAR_DIESEL_MAX_GAP_MIN:
            near.append({"iid": iid, "gap_min": gap_min, "partial": p, "diesel": d})
    near.sort(key=lambda x: x["gap_min"])
    near = near[:MAX_NEAR_DIESEL]

    lines = [
        "# Diagnostics: Partial vs Full (extremes) and Partial EV vs diesel (nearâ€‘match)\n",
        f"*Source: `{PARTIAL_JSON.name}`, `{FULL_JSON.name}`; exclusions: {', '.join(sorted(excl)) or 'none'}.*\n",
    ]
    lines.extend(table_partial_vs_full(top, bottom))
    lines.extend(table_partial_vs_diesel(near))

    lines.append("\n---\n*Regenerate: `python base scenario/generate_diagnostic_tables.py`*\n")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_MD} ({len(top)}+{len(bottom)} Full/Partial extremes; {len(near)} near-diesel)")


if __name__ == "__main__":
    main()
