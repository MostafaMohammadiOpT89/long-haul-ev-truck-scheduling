# Summary: route times, stops, breaks, rests, charging & synchronization

**Configuration for EV labeling (Full & Partial columns in this project):**
battery 750 kWh, CS spacing 60 km, charging power 350 kW, consumption 1.49 kWh/km. Diesel proxy = partial_labeling with very large battery (unconstrained lower bound). Greedy uses the appended/unified greedy run parameters (may differ if greedy comes from another export).

Greedy / diesel-proxy columns use the corresponding run parameters. Timeline-derived charging/sync fields are blank when `activity_timeline` was missing.

Wide CSV column names: `{strategy}_{metric}` with strategies `full`, `partial`, `greedy`, `diesel_proxy`.

## Route times (hours) â€” preview

| instance | id | full_route_h | partial_route_h | greedy_route_h | diesel_proxy_route_h |
| --- | --- | --- | --- | --- | --- |
| short_cl1_cu2 | S_cl1_cu2_B | 31.7317 | 31.4917 | 54.0279 | 30.9 |
| short_cl1_cu4 | S_cl1_cu4_B | 31.0989 | 30.9389 |  | 30.6835 |
| short_cl2_cu2_Balanced | S_cl2_cu2_B |  |  | 47.7292 |  |
| short_cl2_cu2_Unbalanced | S_cl2_cu2_U |  |  | 47.6178 |  |
| short_cl2_cu3_Balanced | S_cl2_cu3_B | 27.2703 | 27.1903 | 28.3493 | 27.1903 |
| short_cl2_cu4_Balanced | S_cl2_cu4_B | 44.35 | 44.19 | 60.633 | 44.19 |
| short_cl2_cu4_Unbalanced | S_cl2_cu4_U | 27.936 | 27.856 | 29.0948 | 27.856 |
| short_cl2_cu5_Balanced | S_cl2_cu5_B | 30.8819 | 30.7219 | 47.9719 | 30.4664 |
| short_cl3_cu10_Balanced | S_cl3_cu10_B | 44.3623 | 44.2023 | 56.3492 | 44.2023 |
| short_cl3_cu12_Balanced | S_cl3_cu12_B | 43.6897 | 43.5297 | 53.1666 | 43.5297 |
| short_cl3_cu12_Unbalanced | S_cl3_cu12_U | 30.5734 | 30.158 | 51.846 | 30.158 |
| short_cl3_cu3_Balanced | S_cl3_cu3_B | 31.3537 | 30.8583 | 50.52 | 30.6029 |
| short_cl3_cu4_Balanced | S_cl3_cu4_B | 31.181 | 31.021 | 52.8969 | 30.7656 |
| short_cl3_cu4_Unbalanced | S_cl3_cu4_U | 27.2186 | 27.1386 | 32.4444 | 27.1386 |
| short_cl3_cu5_Balanced | S_cl3_cu5_B | 44.4808 | 44.3208 | 45.2553 | 44.3208 |
| med_cl1_cu2 | M_cl1_cu2_B | 86.3989 | 85.9189 | 106.7878 | 85.4395 |
| med_cl1_cu4 | M_cl1_cu4_B | 86.5946 | 86.1146 | 118.4067 | 85.7315 |
| med_cl2_cu2_Balanced | M_cl2_cu2_B | 70.5013 | 70.1813 | 108.3501 | 69.9258 |
| med_cl2_cu2_Unbalanced | M_cl2_cu2_U | 69.5276 | 68.9521 | 111.8491 | 68.9521 |
| med_cl2_cu3_Balanced | M_cl2_cu3_B | 89.8041 | 89.1486 | 144.447 | 88.3986 |
| med_cl2_cu4_Balanced | M_cl2_cu4_B | 67.4606 | 67.0606 | 94.151 | 66.5498 |
| med_cl2_cu4_Unbalanced | M_cl2_cu4_U | 87.6357 | 87.1557 | 126.3442 | 86.6448 |
| med_cl2_cu5_Balanced | M_cl2_cu5_B | 72.0894 | 71.6894 | 115.0178 | 71.2937 |
| med_cl3_cu11_Balanced | M_cl3_cu11_B | 52.5003 | 51.8335 | 79.4084 | 51.3297 |
| med_cl3_cu13_Balanced | M_cl3_cu13_B | 56.5258 | 55.8605 | 81.5381 | 52.8605 |
| med_cl3_cu13_Unbalanced | M_cl3_cu13_U | 70.8762 | 70.5562 | 109.7695 | 70.3007 |
| med_cl3_cu3_Balanced | M_cl3_cu3_B | 85.035 | 84.635 | 118.8796 | 84.3796 |
| med_cl3_cu4_Balanced | M_cl3_cu4_B | 64.1811 | 63.9411 | 83.0557 | 63.9411 |
| med_cl3_cu4_Unbalanced | M_cl3_cu4_U | 64.3395 | 64.0995 | 88.1226 | 64.0995 |
| med_cl3_cu5_Balanced | M_cl3_cu5_B | 88.2072 | 87.8872 | 132.7526 | 87.1372 |
| long_cl1_cu2 | L_cl1_cu2_B | 127.4867 | 126.9866 | 157.098 | 126.2567 |
| long_cl1_cu4 | L_cl1_cu4_B | 127.5599 | 127.0799 | 168.5339 | 126.3299 |
| long_cl2_cu2_Balanced | L_cl2_cu2_B | 138.0265 | 136.7947 | 198.274 | 134.2362 |
| long_cl2_cu2_Unbalanced | L_cl2_cu2_U | 151.0793 | 150.0239 | 218.7016 | 148.763 |
| long_cl2_cu3_Balanced | L_cl2_cu3_B | 137.8742 | 136.8342 | 199.9558 | 135.1363 |
| long_cl2_cu4_Balanced | L_cl2_cu4_B | 132.7744 | 132.0544 | 189.6945 | 131.2881 |
| long_cl2_cu4_Unbalanced | L_cl2_cu4_U | 128.1276 | 127.6476 | 164.0005 | 126.8976 |
| long_cl2_cu5_Balanced | L_cl2_cu5_B | 151.2206 | 150.5006 | 218.0798 | 149.2397 |
| long_cl3_cu12_Balanced | L_cl3_cu12_B | 129.6815 | 129.2015 | 189.7328 | 128.4515 |
| long_cl3_cu12_Unbalanced | L_cl3_cu12_U | 114.2799 | 113.5599 | 172.8516 | 112.6659 |
| long_cl3_cu14_Balanced | L_cl3_cu14_B | 128.6132 | 128.1332 | 178.8771 | 127.3832 |
| long_cl3_cu3_Balanced | L_cl3_cu3_B | 134.4714 | 133.0805 | 203.4974 | 132.3142 |
| long_cl3_cu4_Balanced | L_cl3_cu4_B | 112.4502 | 111.8102 | 162.1619 | 111.044 |
| long_cl3_cu4_Unbalanced | L_cl3_cu4_U | 137.3174 | 135.8277 | 201.0644 | 133.5614 |
| long_cl3_cu5_Balanced | L_cl3_cu5_B | 135.6275 | 134.7475 | 200.2806 | 133.4704 |

## Full table

All metrics per strategy (CS stops, breaks, rests, charges, sync counts, % sync): **`table_summary_route_times_and_activity.csv`**