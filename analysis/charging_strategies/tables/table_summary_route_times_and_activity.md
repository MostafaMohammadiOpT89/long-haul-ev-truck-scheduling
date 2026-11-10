# Summary: route times, stops, breaks, rests, charging & synchronization

**Configuration for EV labeling (Full & Partial columns in this project):**
battery 750 kWh, CS spacing 60 km, charging power 350 kW, consumption 1.49 kWh/km. Diesel proxy = partial_labeling with very large battery (unconstrained lower bound).

Timeline-derived charging/sync fields are blank when `activity_timeline` was missing.

Wide CSV column names: `{strategy}_{metric}` with strategies `full`, `partial`, `diesel_proxy`.

## Route times (hours) — preview

| instance                  | id           |   full_route_h |   partial_route_h |   diesel_proxy_route_h |
|:--------------------------|:-------------|---------------:|------------------:|-----------------------:|
| short_cl1_cu2             | S_cl1_cu2_B  |        31.7317 |           31.4917 |                30.9    |
| short_cl1_cu4             | S_cl1_cu4_B  |        31.0989 |           30.9389 |                30.6835 |
| short_cl2_cu3_Balanced    | S_cl2_cu3_B  |        27.2703 |           27.1903 |                27.1903 |
| short_cl2_cu4_Balanced    | S_cl2_cu4_B  |        44.35   |           44.19   |                44.19   |
| short_cl2_cu4_Unbalanced  | S_cl2_cu4_U  |        27.936  |           27.856  |                27.856  |
| short_cl2_cu5_Balanced    | S_cl2_cu5_B  |        30.8819 |           30.7219 |                30.4664 |
| short_cl3_cu10_Balanced   | S_cl3_cu10_B |        44.3623 |           44.2023 |                44.2023 |
| short_cl3_cu12_Balanced   | S_cl3_cu12_B |        43.6897 |           43.5297 |                43.5297 |
| short_cl3_cu12_Unbalanced | S_cl3_cu12_U |        30.5734 |           30.158  |                30.158  |
| short_cl3_cu3_Balanced    | S_cl3_cu3_B  |        31.3537 |           30.8583 |                30.6029 |
| short_cl3_cu4_Balanced    | S_cl3_cu4_B  |        31.181  |           31.021  |                30.7656 |
| short_cl3_cu4_Unbalanced  | S_cl3_cu4_U  |        27.2186 |           27.1386 |                27.1386 |
| short_cl3_cu5_Balanced    | S_cl3_cu5_B  |        44.4808 |           44.3208 |                44.3208 |
| med_cl1_cu2               | M_cl1_cu2_B  |        86.3989 |           85.9189 |                85.4395 |
| med_cl1_cu4               | M_cl1_cu4_B  |        86.5946 |           86.1146 |                85.7315 |
| med_cl2_cu2_Balanced      | M_cl2_cu2_B  |        70.5013 |           70.1813 |                69.9258 |
| med_cl2_cu2_Unbalanced    | M_cl2_cu2_U  |        69.5276 |           68.9521 |                68.9521 |
| med_cl2_cu3_Balanced      | M_cl2_cu3_B  |        89.8041 |           89.1486 |                88.3986 |
| med_cl2_cu4_Balanced      | M_cl2_cu4_B  |        67.4606 |           67.0606 |                66.5498 |
| med_cl2_cu4_Unbalanced    | M_cl2_cu4_U  |        87.6357 |           87.1557 |                86.6448 |
| med_cl2_cu5_Balanced      | M_cl2_cu5_B  |        72.0894 |           71.6894 |                71.2937 |
| med_cl3_cu11_Balanced     | M_cl3_cu11_B |        52.5003 |           51.8335 |                51.3297 |
| med_cl3_cu13_Balanced     | M_cl3_cu13_B |        56.5258 |           55.8605 |                52.8605 |
| med_cl3_cu13_Unbalanced   | M_cl3_cu13_U |        70.8762 |           70.5562 |                70.3007 |
| med_cl3_cu3_Balanced      | M_cl3_cu3_B  |        85.035  |           84.635  |                84.3796 |
| med_cl3_cu4_Balanced      | M_cl3_cu4_B  |        64.1811 |           63.9411 |                63.9411 |
| med_cl3_cu4_Unbalanced    | M_cl3_cu4_U  |        64.3395 |           64.0995 |                64.0995 |
| med_cl3_cu5_Balanced      | M_cl3_cu5_B  |        88.2072 |           87.8872 |                87.1372 |
| long_cl1_cu2              | L_cl1_cu2_B  |       127.487  |          126.987  |               126.257  |
| long_cl1_cu4              | L_cl1_cu4_B  |       127.56   |          127.08   |               126.33   |
| long_cl2_cu2_Balanced     | L_cl2_cu2_B  |       138.026  |          136.795  |               134.236  |
| long_cl2_cu2_Unbalanced   | L_cl2_cu2_U  |       151.079  |          150.024  |               148.763  |
| long_cl2_cu3_Balanced     | L_cl2_cu3_B  |       137.874  |          136.834  |               135.136  |
| long_cl2_cu4_Balanced     | L_cl2_cu4_B  |       132.774  |          132.054  |               131.288  |
| long_cl2_cu4_Unbalanced   | L_cl2_cu4_U  |       128.128  |          127.648  |               126.898  |
| long_cl2_cu5_Balanced     | L_cl2_cu5_B  |       151.221  |          150.501  |               149.24   |
| long_cl3_cu12_Balanced    | L_cl3_cu12_B |       129.681  |          129.202  |               128.452  |
| long_cl3_cu12_Unbalanced  | L_cl3_cu12_U |       114.28   |          113.56   |               112.666  |
| long_cl3_cu14_Balanced    | L_cl3_cu14_B |       128.613  |          128.133  |               127.383  |
| long_cl3_cu3_Balanced     | L_cl3_cu3_B  |       134.471  |          133.081  |               132.314  |
| long_cl3_cu4_Balanced     | L_cl3_cu4_B  |       112.45   |          111.81   |               111.044  |
| long_cl3_cu4_Unbalanced   | L_cl3_cu4_U  |       137.317  |          135.828  |               133.561  |
| long_cl3_cu5_Balanced     | L_cl3_cu5_B  |       135.627  |          134.748  |               133.47   |

## Full table

All metrics per strategy (CS stops, breaks, rests, charges, sync counts, % sync): **`table_summary_route_times_and_activity.csv`**