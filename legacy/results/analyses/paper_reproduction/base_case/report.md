# Base-Scenario Post-Analysis: EV Routing Strategies

Solution time and optimality: Full vs Partial vs Greedy vs Diesel LB.

---

## 1. Executive Summary

- **Full vs Partial:** Partial better in 43/43 instances, avg improvement 0.61%
- **Partial vs Greedy:** Partial better in 42/42 instances, avg improvement 28.83%
- **Partial (EV) vs diesel proxy:** Mean EV 81.93h vs proxy 81.30h; avg EV time gap 0.71% (proxy faster in 32/43 instances)

**Figures:** `analysis_output_baseScenario/figures/`
**Tables:** `analysis_output_baseScenario/tables/`

---

## 2. Per-instance summary (route times + activity / synchronization)

**EV labeling configuration (Full & Partial):** battery 750 kWh, CS spacing 60 km, charging power 350 kW, consumption 1.49 kWh/km. Diesel proxy = partial_labeling with very large battery (unconstrained lower bound). Greedy uses the appended/unified greedy run parameters (may differ if greedy comes from another export).

- **`table_summary_route_times_and_activity.csv`:** one row per instance; columns `full_*`, `partial_*`, `greedy_*`, `diesel_proxy_*` (route hours, CS stops, breaks, rests, charge counts, sync events, % charging synchronized, timeline sync splits where present).
- **`table_summary_route_times_and_activity.md`:** short markdown preview (route times) + pointer to CSV.

The appendix table (`table_appendix_full_results.csv`) remains available for computation time and label counts.

### Thesis-style & diagnostic analyst tables (CSV)

- **`table_thesis_full_vs_partial_per_instance.csv`** â€” matched EV Full vs Partial: route deltas, sync % / unsync counts / idle minutes, CS stops, breaks, rests, timeline charge counts, SOC text, short interpretation.
- **`table_thesis_full_vs_partial_by_route_class.csv`** â€” means by Short / Medium / Long.
- **`table_diagnostic_partial_vs_full_extremes.csv`** â€” top and bottom instances by `benefit_full_minus_partial_min` (minutes), with key charging/sync columns.
- **`table_diagnostic_near_diesel_wide.csv`** â€” instances with small EV vs diesel-proxy route gap; wide metric columns.
- **`table_thesis_diagnostic_caption.txt`** â€” one-line caption for the above.

---

## 3. Base-Scenario: Total Route Time per Instance (All Four Strategies)

![Main Chart](analysis_output_baseScenario/figures/01_base_scenario_route_time_per_instance.png)

![Avg Route Time by Group](analysis_output_baseScenario/figures/01b_avg_route_time_by_group.png)

![Avg Computation Time by Group](analysis_output_baseScenario/figures/01c_avg_computation_time_by_group.png)

---

## 4. Comparisons: Full vs Partial, Partial vs Greedy, Partial vs Diesel LB

**Figure 2a â€” Mean route time (aggregated)**

![Figure 2a: mean route time comparisons](analysis_output_baseScenario/figures/02a_comparisons_mean_route_time.png)

**Figure 2b â€” Per-instance comparisons**

![Figure 2b: per-instance comparisons](analysis_output_baseScenario/figures/02b_comparisons_per_instance.png)

**Figure 2c â€” Per-instance comparisons (box plots)**

![Figure 2c: per-instance comparison box plots](analysis_output_baseScenario/figures/02c_comparisons_per_instance_boxplots.png)

**Full vs Partial:** Mean route time Full 82.43h, Partial 81.93h; Partial better in 43/43; Avg improvement 0.61%
**Partial vs Greedy:** Mean route time Partial 83.14h, Greedy 119.15h; Partial better in 42/42; Avg improvement 28.83%
**Partial vs diesel proxy (high-battery partial):** Mean EV 81.93h, proxy 81.30h; avg EV gap 0.71%; proxy faster in 32/43 instances.

**Tables:** `table_00_instance_id_map.csv` (id â†” instance name); `table_01_combined_comparisons.csv`; `table_02_per_instance_partial_vs_full.csv`; `table_03_per_instance_partial_vs_diesel_proxy.csv`

---

## 5. Partial vs Full by Problem Size and Balance

![Problem Size](analysis_output_baseScenario/figures/05_problem_size_partial_vs_full.png)

| Size | N | Partial better | Full better | Improvement % | Mean Partial | Mean Full |
|------|---|----------------|-------------|-----------------|--------------|-----------|
| short | 13 | 13 | 0 | 0.6% | 34.1h | 34.3h |
| medium | 15 | 15 | 0 | 0.6% | 73.7h | 74.1h |
| large | 15 | 15 | 0 | 0.6% | 131.6h | 132.4h |

![Balance](analysis_output_baseScenario/figures/06_balance_partial_vs_full.png)

| Balance | N | Partial better | Full better | Avg improvement |
|---------|---|----------------|-------------|-----------------|
| Balanced | 32 | 32 | 0 | 0.6% |
| Unbalanced | 11 | 11 | 0 | 0.6% |

---

## 6. Computation Time by Strategy

![Computation Time](analysis_output_baseScenario/figures/07_computation_time.png)

---

## Charging Synchronization

Per test/configuration: num_charges, num_synchronized, num_unsynchronized, num_sync_with_break, num_sync_with_rest, num_unsynchronized_breaks, num_unsynchronized_rests.

**Table:** `analysis_output_baseScenario/tables/table_charging_sync.csv`

---

## Appendix: Full Results Table

Complete table: instance, route time, computation time, labels generated, labels dominated, charging sync for each strategy.

**Table:** `analysis_output_baseScenario/tables/table_appendix_full_results.csv`
