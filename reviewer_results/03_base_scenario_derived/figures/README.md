# How to read the driver-heuristic figures

Base scenario (750 kWh, 60 km, 350 kW, 1.49 kWh/km), 43 instances.

Per-instance x-axis labels are the short IDs from `../tables/table_D00_instance_id_map.csv`. Dashed vertical lines separate short / medium / long.

| File | What it shows | Matching table |
|---|---|---|
| `D01_route_time_per_instance.png` | Grouped bars: Full, Partial, Driver_FC, Driver_OO, diesel proxy (43 instances) | D02 |
| `D02a_mean_route_time_by_strategy.png` | Mean route time by strategy | D01 / D04 |
| `D02b_per_instance_gaps.png` | Per-instance % gaps: Driver vs Partial, vs diesel | D02 gap columns |
| `D02c_boxplots_gaps.png` | Distribution of those gaps | D02 |
| `D03_avg_route_time_by_group.png` | Means by short / medium / long | D03 |
| `D04_activity_by_strategy.png` | Charging stops, breaks, rests, idle charging | D04 |
| `D05_rule_usage_by_group.png` | Which Driver rule opened the stops (Rule 2 / 3 / 4), by problem size | D05 |
| `D06_tsync_sensitivity.png` | Driver_FC and Driver_OO mean route time vs `t_sync` (means on the 43 instances common with Partial) | D06, column `mean_route_h_common_with_partial` |

Column-level definitions: `../tables/README.md`.
