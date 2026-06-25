"""
Label dominance for Partial Recharge (interval labels).

When ``cp`` (charging power kW) is provided, uses a paper-style trade-off check:
- HoS / monotone resources compared componentwise (latest reversed).
- Energy: L1 dominates L2 only if L1's battery-vs-time segment covers L2's
  at L2's left endpoint and L1's max battery is at least L2's max.

If ``cp`` is None or 0, falls back to the legacy componentwise tuple on
``time_min`` and ``reqRT_min`` only (faster but can prune too aggressively).
"""
from collections import defaultdict

import numpy as np
from functools import lru_cache

EPS = 1e-9


def battery_at(label, t, cp):
    """
    Battery (kWh) available if the label is realized at clock time t (hours).
    Linear charge between time_min and time_max at slope cp; saturate at remainingBattery_max.
    """
    if cp is None or cp <= 0:
        return label.remainingBattery_min

    if t <= label.time_min + EPS:
        return label.remainingBattery_min

    effective_t = min(t, label.time_max)
    b = label.remainingBattery_min + cp * max(0.0, effective_t - label.time_min)
    return min(label.remainingBattery_max, b)


def hos_dominate(l1, l2):
    return (
        l1.timeToNext <= l2.timeToNext + EPS
        and l1.drive_R <= l2.drive_R + EPS
        and l1.drive_B <= l2.drive_B + EPS
        and l1.elapsed_R <= l2.elapsed_R + EPS
        and l1.elapsed_B <= l2.elapsed_B + EPS
        and l1.latest_R + EPS >= l2.latest_R
        and l1.latest_B + EPS >= l2.latest_B
    )


def energy_curve_dominate(l1, l2, cp):
    if l1.time_min > l2.time_min + EPS:
        return False
    if battery_at(l1, l2.time_min, cp) + EPS < l2.remainingBattery_min:
        return False
    if l1.remainingBattery_max + EPS < l2.remainingBattery_max:
        return False
    return True


def label_dominates(l1, l2, cp):
    if l1.detailedPath[-1] != l2.detailedPath[-1]:
        return False
    return hos_dominate(l1, l2) and energy_curve_dominate(l1, l2, cp)


def _dominate_curve(label_list, cp):
    dominated = set()

    buckets = defaultdict(list)
    for idx, lab in enumerate(label_list):
        buckets[lab.detailedPath[-1]].append((idx, lab))

    for _, items in buckets.items():
        items.sort(
            key=lambda x: (
                x[1].time_min,
                x[1].drive_R,
                x[1].drive_B,
                x[1].elapsed_R,
                x[1].elapsed_B,
                -(x[1].latest_R if x[1].latest_R != float("inf") else 1e30),
                -(x[1].latest_B if x[1].latest_B != float("inf") else 1e30),
                -x[1].remainingBattery_max,
            )
        )

        for a in range(len(items)):
            i, li = items[a]
            if i in dominated:
                continue
            for b in range(a + 1, len(items)):
                j, lj = items[b]
                if j in dominated:
                    continue

                if label_dominates(li, lj, cp):
                    dominated.add(j)
                elif label_dominates(lj, li, cp):
                    dominated.add(i)
                    break

    return list(dominated)


def array_to_tuple(array):
    return tuple(map(tuple, array))


@lru_cache(None)
def compare_labels(current_attrs, other_attrs):
    is_current_dominated = np.all(np.array(current_attrs) <= np.array(other_attrs))
    is_other_dominated = np.all(np.array(other_attrs) <= np.array(current_attrs))
    return is_current_dominated, is_other_dominated


def _dominate_legacy(labelList):
    dominatedLabels = []
    label_attrs = []

    for lab in labelList:
        attrs = (
            lab.time_min,
            lab.timeToNext,
            lab.drive_R,
            lab.drive_B,
            lab.elapsed_R,
            lab.elapsed_B,
            -lab.latest_R,
            -lab.latest_B,
            lab.reqRT_min,
        )
        label_attrs.append(attrs)

    label_attrs = array_to_tuple(label_attrs)

    for i in range(len(labelList) - 1):
        for j in range(i + 1, len(labelList)):
            if labelList[i].detailedPath[-1] == labelList[j].detailedPath[-1]:
                is_current_dominated, is_other_dominated = compare_labels(
                    label_attrs[i], label_attrs[j]
                )

                if is_current_dominated:
                    dominatedLabels.append(j)
                elif is_other_dominated:
                    dominatedLabels.append(i)
                    break
    return list(set(dominatedLabels))


def dominate(labelList, cp=None):
    """
    Return indices of dominated labels in ``labelList`` (same contract as before).

    Parameters
    ----------
    labelList : list[Label]
    cp : float | None
        Charging power (kW). If > 0, use curve + HoS dominance; else legacy.
    """
    if not labelList:
        return []
    if cp is not None and cp > 0:
        return _dominate_curve(labelList, cp)
    return _dominate_legacy(labelList)
