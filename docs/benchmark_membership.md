# Problem to resolve with colleagues: benchmark membership

The manuscript appendix and the saved base-case results each contain 43
instances, but they are not the same 43. The repository contains 45 stored
instance folders (15 short, 15 medium, and 15 long).

| Source | Short | Medium | Long | Total | Missing from the stored pool |
| --- | ---: | ---: | ---: | ---: | --- |
| Current appendix (active rows) | 14 | 15 | 14 | 43 | `short_cl1_cu4`, `long_cl1_cu2` |
| Saved base-case results | 13 | 15 | 15 | 43 | `short_cl2_cu2_Balanced`, `short_cl2_cu2_Unbalanced` |

The two lists overlap on 41 instances; together they cover all 45. The
`short_cl1_cu4` appendix row is commented out; `long_cl1_cu2` is absent.
The reason for these differences is not established.

The balanced and unbalanced two-cluster/two-customer instances both allocate
one customer to each cluster. However, their stored distances and service times
differ: they are not identical input files. The same allocation issue also
occurs for the medium and long variants, so it does not by itself explain
excluding only the two short instances.

**Question for colleagues:** Which instances were intended for the final study,
and why were these four instances treated differently in the appendix and the
saved results? Were any cases excluded deliberately, or are results/table rows
simply missing? Please also confirm that the appendix statistics correspond to
the input versions used in the experiments.

## Interim solution

Keep membership unresolved. Include all 45 stored instances in the consolidated
files for each observed parameter/policy setting, including settings without
results for some instances. Also include placeholder rows for the confirmed
500 kWh / 350 kW / 50 km / 1.49 kWh/km electric base case. No scheduling
experiments are rerun, and no outcomes are fabricated.

`in_current_appendix` and `in_saved_base_case` preserve the conflicting
memberships as descriptive flags, not selection rules. `record_status` separates
available records from `no_record_available`; the latter has blank outcome
columns and an empty observation list. Missing does not mean infeasible.

The complete grid means each *observed joint parameter/policy setting* crossed
with all 45 stored instances. It does not create every arbitrary cross-product
of individual parameter values or claim those settings were ever executed.

See [result_files.md](result_files.md) for file locations and provenance.
