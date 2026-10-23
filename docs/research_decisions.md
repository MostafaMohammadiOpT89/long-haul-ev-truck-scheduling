# Research decisions requiring scientific review

The restructuring preserves computational methods and inherited data. It does not reconcile these scientific discrepancies automatically.

1. **Instance membership.** `benchmark_v1` contains 45 instances. Manuscript section 4.1 says 42. The saved base unified bundle contains 43 (missing `short_cl2_cu2_Balanced` and `short_cl2_cu2_Unbalanced`). The saved parameter-sweep unified bundle contains 36. These counts describe saved files, not proof of complete experiments. The base analysis has no active exclusion list. Choose and record the intended paper instance set before regenerating publication results.
2. **Base parameters.** Manuscript Table 5 specifies 500 kWh and 50 km. Existing analysis and the inherited `paper_base` preset use 750 kWh and 60 km. `legacy_base` retains a third experimental configuration. No parameter values were changed to reconcile these.
3. **Generator provenance.** The generator dataset shares names and instance TXT files with the benchmark, but 147 matrices/diagnostics differ. Both versions are preserved through the catalog. Identify which generator/configuration/seed produced each before treating regeneration as equivalent.
4. **Historical result provenance.** The principal base and sweep JSON bundles name raw cluster files absent from the inherited checkout. Their algorithm revision and exact input hashes cannot be established retrospectively from those bundles. Imported manifests mark this uncertainty; new manifests record source and input hashes.
5. **Legacy algorithms.** The full-tree greedy scheduler differs from the active partial-tree scheduler. Older runners also have different runtime limits (for example `optAlgo.py` versus the single-scenario runner). They are retained for review, not merged based on similar filenames.
6. **Paper heuristics.** The manuscript discusses a restricted-labeling heuristic as well as a driver-inspired heuristic. The supported current experiment methods are partial labeling, full labeling, greedy, and driver heuristic. No new scientific algorithm was introduced by the migration.

The new `station_spacing` and `driver_sync_sweep` presets expose the inherited study dimensions. Their explicit grids are reviewable configurations; they are not claims that every saved historical result was produced by these exact presets.

7. **Inherited comparisons use differing charging powers.** Re-running the original driver analysis reports that its loaded greedy results used 150 kW, whereas the labeling base case used 350 kW. Sensitivity analysis also reports negative EV-minus-diesel gaps for some pairs. These pre-existing inconsistencies require review before interpreting the comparisons as controlled experiments.

8. **Synchronization definitions.** The metrics document describes time-overlap synchronization, while inherited post-analysis code also calculates sequence-based synchronization. Both implementations were preserved. Review which definition should govern the final paper before unifying metric calculations.
