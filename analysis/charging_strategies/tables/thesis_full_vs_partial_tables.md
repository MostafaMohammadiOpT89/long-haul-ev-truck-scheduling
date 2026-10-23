# Full vs Partial â€” thesis tables (EV runs, matched by `instance_id`)

*Paired rows: **43** instances; excluded (same as main analysis): .*

## Table 1 â€” All test instances

| Instance | Route time effect | Synchronization effect | End-of-route SOC effect | Short interpretation |
| --- | --- | --- | --- | --- |
| `short_cl1_cu2` | Partial faster by 14.4 min | No change | No change | Partial faster; sync and SOC comparable |
| `short_cl1_cu4` | Partial faster by 9.6 min | No change | No change | Partial faster; sync and SOC comparable |
| `short_cl2_cu3_Balanced` | Partial faster by 4.8 min | No change | No change | Partial faster; sync and SOC comparable |
| `short_cl2_cu4_Balanced` | Partial faster by 9.6 min | No change | No change | Partial faster; sync and SOC comparable |
| `short_cl2_cu4_Unbalanced` | Partial faster by 4.8 min | No change | Partial ends with SOC range 414.2â€“471.2 kWh vs fixed Full 151.7 kWh | Partial faster; interval SOC vs fixed Full |
| `short_cl2_cu5_Balanced` | Partial faster by 9.6 min | No change | No change | Partial faster; sync and SOC comparable |
| `short_cl3_cu10_Balanced` | Partial faster by 9.6 min | No change | Partial ends with 338.8 kWh more SOC | Mixed effects |
| `short_cl3_cu12_Balanced` | Partial faster by 9.6 min | No change | No change | Partial faster; sync and SOC comparable |
| `short_cl3_cu12_Unbalanced` | Partial faster by 24.9 min | +50.0 pp sync, 1 fewer unsync charge, 15.3 min less idle charging | No change | Partial improves time and synchronization |
| `short_cl3_cu3_Balanced` | Partial faster by 29.7 min | +33.3 pp sync, 1 fewer unsync charge, 15.3 min less idle charging | No change | Partial improves time and synchronization |
| `short_cl3_cu4_Balanced` | Partial faster by 9.6 min | +16.7 pp sync | No change | Partial improves time and synchronization |
| `short_cl3_cu4_Unbalanced` | Partial faster by 4.8 min | No change | No change | Partial faster; sync and SOC comparable |
| `short_cl3_cu5_Balanced` | Partial faster by 9.6 min | No change | Partial ends with 89.4 kWh more SOC | Mixed effects |
| `med_cl1_cu2` | Partial faster by 28.8 min | +8.3 pp sync | Partial ends with SOC range 297.0â€“392.1 kWh vs fixed Full 34.5 kWh | Partial improves time and sync; interval SOC |
| `med_cl1_cu4` | Partial faster by 28.8 min | +4.8 pp sync | No change | Partial improves time and synchronization |
| `med_cl2_cu2_Balanced` | Partial faster by 19.2 min | +8.3 pp sync | No change | Partial improves time and synchronization |
| `med_cl2_cu2_Unbalanced` | Partial faster by 34.5 min | +25.0 pp sync, 1 fewer unsync charge, 15.3 min less idle charging | No change | Partial improves time and synchronization |
| `med_cl2_cu3_Balanced` | Partial faster by 39.3 min | +20.0 pp sync, 1 fewer unsync charge, 15.3 min less idle charging | Partial ends with SOC range 258.2â€“353.3 kWh vs fixed Full 85.1 kWh | Partial improves time and sync; interval SOC |
| `med_cl2_cu4_Balanced` | Partial faster by 24.0 min | No change | No change | Partial faster; sync and SOC comparable |
| `med_cl2_cu4_Unbalanced` | Partial faster by 28.8 min | +8.3 pp sync | No change | Partial improves time and synchronization |
| `med_cl2_cu5_Balanced` | Partial faster by 24.0 min | +6.7 pp sync | No change | Partial improves time and synchronization |
| `med_cl3_cu11_Balanced` | Partial faster by 40.0 min | +30.0 pp sync, 1 fewer unsync charge, 20.8 min less idle charging | No change | Partial improves time and synchronization |
| `med_cl3_cu13_Balanced` | Partial faster by 39.9 min | +20.0 pp sync, 1 fewer unsync charge, 105.9 min less idle charging | Partial ends with SOC range 177.5â€“659.7 kWh vs fixed Full 7.9 kWh | Partial improves time and sync; interval SOC |
| `med_cl3_cu13_Unbalanced` | Partial faster by 19.2 min | +8.3 pp sync | Partial ends with 89.4 kWh more SOC | Partial improves time and synchronization |
| `med_cl3_cu3_Balanced` | Partial faster by 24.0 min | +5.7 pp sync | No change | Partial improves time and synchronization |
| `med_cl3_cu4_Balanced` | Partial faster by 14.4 min | No change | No change | Partial faster; sync and SOC comparable |
| `med_cl3_cu4_Unbalanced` | Partial faster by 14.4 min | No change | No change | Partial faster; sync and SOC comparable |
| `med_cl3_cu5_Balanced` | Partial faster by 19.2 min | No change | Partial ends with SOC range 407.8â€“502.9 kWh vs fixed Full 145.3 kWh | Partial faster; interval SOC vs fixed Full |
| `long_cl1_cu2` | Partial faster by 30.0 min | -27.3 pp sync, 3 more unsync charges, 43.8 min more idle charging | Partial ends with 89.4 kWh less SOC | Partial faster despite weaker sync metrics |
| `long_cl1_cu4` | Partial faster by 28.8 min | No change | Partial ends with SOC range 473.9â€“569.0 kWh vs fixed Full 122.0 kWh | Partial faster; interval SOC vs fixed Full |
| `long_cl2_cu2_Balanced` | Partial faster by 73.9 min | -1.2 pp sync, 1 more unsync charge, 16.3 min less idle charging | No change | Partial improves time and synchronization |
| `long_cl2_cu2_Unbalanced` | Partial faster by 63.3 min | +15.7 pp sync, 1 fewer unsync charge, 15.3 min less idle charging | Partial ends with SOC range 261.5â€“356.6 kWh vs fixed Full 88.4 kWh | Partial improves time and sync; interval SOC |
| `long_cl2_cu3_Balanced` | Partial faster by 62.4 min | No change | No change | Partial faster; sync and SOC comparable |
| `long_cl2_cu4_Balanced` | Partial faster by 43.2 min | +10.3 pp sync | Partial ends with SOC range 263.0â€“358.1 kWh vs fixed Full 0.5 kWh | Partial improves time and sync; interval SOC |
| `long_cl2_cu4_Unbalanced` | Partial faster by 28.8 min | No change | No change | Partial faster; sync and SOC comparable |
| `long_cl2_cu5_Balanced` | Partial faster by 43.2 min | +7.9 pp sync | No change | Partial improves time and synchronization |
| `long_cl3_cu12_Balanced` | Partial faster by 28.8 min | No change | No change | Partial faster; sync and SOC comparable |
| `long_cl3_cu12_Unbalanced` | Partial faster by 43.2 min | +4.4 pp sync | No change | Partial improves time and synchronization |
| `long_cl3_cu14_Balanced` | Partial faster by 28.8 min | No change | Partial ends with SOC range 295.7â€“390.8 kWh vs fixed Full 33.2 kWh | Partial faster; interval SOC vs fixed Full |
| `long_cl3_cu3_Balanced` | Partial faster by 83.5 min | +22.4 pp sync, 2 fewer unsync charges, 30.7 min less idle charging | Partial ends with SOC range 289.3â€“384.4 kWh vs fixed Full 26.8 kWh | Partial improves time and sync; interval SOC |
| `long_cl3_cu4_Balanced` | Partial faster by 38.4 min | +10.2 pp sync | Partial ends with SOC range 307.8â€“402.9 kWh vs fixed Full 45.3 kWh | Partial improves time and sync; interval SOC |
| `long_cl3_cu4_Unbalanced` | Partial faster by 89.4 min | +20.2 pp sync, 2 fewer unsync charges, 76.8 min less idle charging | Partial ends with SOC range 255.0â€“350.1 kWh vs fixed Full 81.9 kWh | Partial improves time and sync; interval SOC |
| `long_cl3_cu5_Balanced` | Partial faster by 52.8 min | +7.0 pp sync | Partial ends with SOC range 301.0â€“396.1 kWh vs fixed Full 38.5 kWh | Partial improves time and sync; interval SOC |

## Table 2 â€” Averages by route class

| Group | Average route time effect | Average synchronization effect | Average SOC effect | Group-level interpretation |
| --- | --- | --- | --- | --- |
| **Short** (13) | Partial faster on average by 11.6 min | +7.7 pp sync, 0.2 fewer unsync charges, 2.4 min less idle charging | Partial often ends with higher SOC, sometimes as an interval | Partial improves time and synchronization on average |
| **Medium** (15) | Partial faster on average by 26.6 min | +9.7 pp sync, 0.3 fewer unsync charges, 10.5 min less idle charging | Partial yields more flexible end SOC in several cases | Partial improves time and synchronization on average |
| **Long** (15) | Partial faster on average by 49.2 min | +4.6 pp sync, 0.1 fewer unsync charges, 6.4 min less idle charging | Partial often ends with interval SOC vs fixed Full | Partial offers noticeable benefits on long routes |

## Insights

- Across **43** EV instances, Partial matches or improves total route time in most cases, with small mean shifts by horizon.
- Synchronization metrics (sync rate, unsynchronized charging events, idle charging time) often move in Partialâ€™s favor where charging is less rigid than full recharge.
- End-of-route SOC is sometimes an interval under Partial, reflecting multiple label-optimal energy outcomes rather than a single fixed terminal SOC.
- Medium and long route classes tend to show the largest average gains in coordination metrics; short routes are frequently already near the ceiling for sync rate.
- The full per-instance table belongs in the appendix; the grouped table supports the main textâ€™s summary of route-class patterns.

## Summary paragraph

Most instances exhibit small route-time differences between Full and Partial labeling, with many classified as **no change** at the reported precision. The main advantages of Partial appear in more demanding settingsâ€”especially where partial recharge relaxes timingâ€”through **higher synchronization rates**, **fewer unsynchronized charging events**, and **lower idle charging time**, occasionally accompanied by modest route-time improvements. Terminal SOC is often identical between strategies, but Partial sometimes reports a **feasible SOC band** instead of a single value, which is informative for implementation flexibility. The grouped averages align with this pattern: **Medium** and **Long** rows show somewhat stronger average synchronization gains than **Short** rows. Readers should consult the appendix table for instance-level detail and the `table_00_instance_id_map.csv` codes where cross-referencing figures.
