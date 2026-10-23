# Diagnostics: Partial vs Full (extremes) and Partial EV vs diesel (nearâ€‘match)

*Source: `details.jsonl`, `details.jsonl`; exclusions: none.*

## Diagnostic A â€” Partial vs Full (extreme cases)

*Largest **5** gains and **5** smallest gains in route time (minutes saved by Partial = (Full âˆ’ Partial)Ã—60). Excluded instances omitted.*

### A.1 Strongest Partial advantage

| Instance | Î” route (min) | Full sync % | Partial sync % | Î” idle (min) | Why Partial wins (diagnostic) | When Full still matters |
| --- | --- | --- | --- | --- | --- | --- |
| `long_cl3_cu4_Unbalanced` | +89.4 | 58.3 | 78.6 | 76.8 | Idle charging cut by ~76.8 min vs Full. Much higher charging-event sync under Partial. 2 fewer unsynchronized charging event(s). | Reference baseline; use if policy requires full recharge only. |
| `long_cl3_cu3_Balanced` | +83.5 | 54.5 | 76.9 | 30.7 | Idle charging cut by ~30.7 min vs Full. Much higher charging-event sync under Partial. 2 fewer unsynchronized charging event(s). | Reference baseline; use if policy requires full recharge only. |
| `long_cl2_cu2_Balanced` | +73.9 | 58.3 | 57.1 | 16.3 | Idle charging cut by ~16.3 min vs Full. | Reference baseline; use if policy requires full recharge only. |
| `long_cl2_cu2_Unbalanced` | +63.3 | 70.0 | 85.7 | 15.3 | Idle charging cut by ~15.3 min vs Full. Much higher charging-event sync under Partial. 1 fewer unsynchronized charging event(s). | Reference baseline; use if policy requires full recharge only. |
| `long_cl2_cu3_Balanced` | +62.4 | 46.2 | 46.2 | 0.0 | Makespan gain with comparable sync counters; check timeline / SOC flexibility. | Reference baseline; use if policy requires full recharge only. |

### A.2 Weakest Partial advantage (or Full faster)

| Instance | Î” route (min) | Full sync % | Partial sync % | Î” idle (min) | Why little gain / Full ahead | How to leverage Full more |
| --- | --- | --- | --- | --- | --- | --- |
| `short_cl3_cu4_Unbalanced` | +4.8 | 100.0 | 100.0 | 0.0 | Sync rate already at ceiling for both; little room for Partial to differentiate. No unsynchronized charging in either run. Idle charging nearly the same. | Prefer Full when minimizing makespan dominates and sync headroom is low. |
| `short_cl2_cu4_Unbalanced` | +4.8 | 100.0 | 100.0 | 0.0 | Sync rate already at ceiling for both; little room for Partial to differentiate. No unsynchronized charging in either run. Idle charging nearly the same. | Prefer Full when minimizing makespan dominates and sync headroom is low. |
| `short_cl2_cu3_Balanced` | +4.8 | 100.0 | 100.0 | 0.0 | Sync rate already at ceiling for both; little room for Partial to differentiate. No unsynchronized charging in either run. Idle charging nearly the same. | Prefer Full when minimizing makespan dominates and sync headroom is low. |
| `short_cl3_cu5_Balanced` | +9.6 | 100.0 | 100.0 | 0.0 | Sync rate already at ceiling for both; little room for Partial to differentiate. No unsynchronized charging in either run. Idle charging nearly the same. | Prefer Full when minimizing makespan dominates and sync headroom is low. |
| `short_cl3_cu4_Balanced` | +9.6 | 50.0 | 66.7 | -0.0 | Idle charging nearly the same. | Prefer Full when minimizing makespan dominates and sync headroom is low. |

## Diagnostic B â€” Partial EV vs diesel proxy (nearâ€‘diesel routes)

*Instances with **|route_EV âˆ’ route_diesel|Ã—60 â‰¤ 15 min**; up to **6** tightest matches. Diesel = highâ€‘battery partial row.*

### `short_cl2_cu3_Balanced` â€” EV excess vs diesel: **0.0 min**

| Metric | Diesel proxy | Partial EV | Î” (EV âˆ’ diesel) |
| --- | --- | --- | --- |
| Route time (h) | 27.19 | 27.19 | 0.0 |
| Sync % | 0.0 | 100.0 | 100.0 |
| Unsync charging events | 0 | 0 | 0 |
| Idle charging (min) | 0.0 | 0.0 | 0.0 |
| Synchronized events | 0 | 2 | 2 |
| CS stops | 0 | 2 | 2 |
| Breaks | 2 | 2 | 0 |
| Rests | 1 | 1 | 0 |
| Restâ€‘sync charging | 0 | 1 | 1 |
| Break fullâ€‘sync chg. | 0 | 0 | 0 |
| Break partialâ€‘sync chg. | 0 | 1 | 1 |
| Break sync chg. (any) | 0 | 1 | 1 |
| Unsync breaks | 2 | 2 | 0 |
| Unsync rests | 1 | 1 | 0 |

*Makespan essentially matches unconstrained energy (diesel proxy). Idle charging is not inflated vs proxy. Same unsynchronized charging count as proxy.*

### `short_cl2_cu4_Balanced` â€” EV excess vs diesel: **0.0 min**

| Metric | Diesel proxy | Partial EV | Î” (EV âˆ’ diesel) |
| --- | --- | --- | --- |
| Route time (h) | 44.19 | 44.19 | 0.0 |
| Sync % | 100.0 | 100.0 | 0.0 |
| Unsync charging events | 0 | 0 | 0 |
| Idle charging (min) | 0.0 | 0.0 | 0.0 |
| Synchronized events | 2 | 2 | 0 |
| CS stops | 2 | 2 | 0 |
| Breaks | 2 | 2 | 0 |
| Rests | 2 | 2 | 0 |
| Restâ€‘sync charging | 1 | 2 | 1 |
| Break fullâ€‘sync chg. | 0 | 0 | 0 |
| Break partialâ€‘sync chg. | 1 | 0 | -1 |
| Break sync chg. (any) | 1 | 0 | -1 |
| Unsync breaks | 2 | 2 | 0 |
| Unsync rests | 2 | 2 | 0 |

*Makespan essentially matches unconstrained energy (diesel proxy). Charging synchronization stays comparable to the proxy despite finite battery. Idle charging is not inflated vs proxy. Same unsynchronized charging count as proxy.*

### `short_cl2_cu4_Unbalanced` â€” EV excess vs diesel: **0.0 min**

| Metric | Diesel proxy | Partial EV | Î” (EV âˆ’ diesel) |
| --- | --- | --- | --- |
| Route time (h) | 27.856 | 27.856 | 0.0 |
| Sync % | 0.0 | 100.0 | 100.0 |
| Unsync charging events | 0 | 0 | 0 |
| Idle charging (min) | 0.0 | 0.0 | 0.0 |
| Synchronized events | 0 | 3 | 3 |
| CS stops | 0 | 3 | 3 |
| Breaks | 2 | 2 | 0 |
| Rests | 1 | 1 | 0 |
| Restâ€‘sync charging | 0 | 1 | 1 |
| Break fullâ€‘sync chg. | 0 | 0 | 0 |
| Break partialâ€‘sync chg. | 0 | 2 | 2 |
| Break sync chg. (any) | 0 | 2 | 2 |
| Unsync breaks | 2 | 2 | 0 |
| Unsync rests | 1 | 1 | 0 |

*Makespan essentially matches unconstrained energy (diesel proxy). Idle charging is not inflated vs proxy. Same unsynchronized charging count as proxy.*

### `short_cl3_cu10_Balanced` â€” EV excess vs diesel: **0.0 min**

| Metric | Diesel proxy | Partial EV | Î” (EV âˆ’ diesel) |
| --- | --- | --- | --- |
| Route time (h) | 44.202 | 44.202 | 0.0 |
| Sync % | 100.0 | 100.0 | 0.0 |
| Unsync charging events | 0 | 0 | 0 |
| Idle charging (min) | 0.0 | 0.0 | 0.0 |
| Synchronized events | 1 | 4 | 3 |
| CS stops | 1 | 4 | 3 |
| Breaks | 2 | 2 | 0 |
| Rests | 2 | 2 | 0 |
| Restâ€‘sync charging | 1 | 2 | 1 |
| Break fullâ€‘sync chg. | 0 | 0 | 0 |
| Break partialâ€‘sync chg. | 0 | 2 | 2 |
| Break sync chg. (any) | 0 | 2 | 2 |
| Unsync breaks | 2 | 2 | 0 |
| Unsync rests | 2 | 2 | 0 |

*Makespan essentially matches unconstrained energy (diesel proxy). Charging synchronization stays comparable to the proxy despite finite battery. Idle charging is not inflated vs proxy. Same unsynchronized charging count as proxy.*

### `short_cl3_cu12_Balanced` â€” EV excess vs diesel: **0.0 min**

| Metric | Diesel proxy | Partial EV | Î” (EV âˆ’ diesel) |
| --- | --- | --- | --- |
| Route time (h) | 43.53 | 43.53 | 0.0 |
| Sync % | 0.0 | 100.0 | 100.0 |
| Unsync charging events | 0 | 0 | 0 |
| Idle charging (min) | 0.0 | 0.0 | 0.0 |
| Synchronized events | 0 | 4 | 4 |
| CS stops | 0 | 4 | 4 |
| Breaks | 2 | 2 | 0 |
| Rests | 2 | 2 | 0 |
| Restâ€‘sync charging | 0 | 2 | 2 |
| Break fullâ€‘sync chg. | 0 | 0 | 0 |
| Break partialâ€‘sync chg. | 0 | 2 | 2 |
| Break sync chg. (any) | 0 | 2 | 2 |
| Unsync breaks | 2 | 2 | 0 |
| Unsync rests | 2 | 2 | 0 |

*Makespan essentially matches unconstrained energy (diesel proxy). Idle charging is not inflated vs proxy. Same unsynchronized charging count as proxy.*

### `short_cl3_cu12_Unbalanced` â€” EV excess vs diesel: **0.0 min**

| Metric | Diesel proxy | Partial EV | Î” (EV âˆ’ diesel) |
| --- | --- | --- | --- |
| Route time (h) | 30.158 | 30.158 | 0.0 |
| Sync % | 100.0 | 100.0 | 0.0 |
| Unsync charging events | 0 | 0 | 0 |
| Idle charging (min) | 0.0 | 0.0 | 0.0 |
| Synchronized events | 1 | 2 | 1 |
| CS stops | 1 | 2 | 1 |
| Breaks | 2 | 2 | 0 |
| Rests | 1 | 1 | 0 |
| Restâ€‘sync charging | 0 | 1 | 1 |
| Break fullâ€‘sync chg. | 0 | 0 | 0 |
| Break partialâ€‘sync chg. | 1 | 1 | 0 |
| Break sync chg. (any) | 1 | 1 | 0 |
| Unsync breaks | 2 | 2 | 0 |
| Unsync rests | 1 | 1 | 0 |

*Makespan essentially matches unconstrained energy (diesel proxy). Charging synchronization stays comparable to the proxy despite finite battery. Idle charging is not inflated vs proxy. Same unsynchronized charging count as proxy.*


---
*Regenerate: `python base scenario/generate_diagnostic_tables.py`*
