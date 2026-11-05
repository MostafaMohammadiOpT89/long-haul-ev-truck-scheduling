# Research decisions

Paper methods: Full recharge, Partial recharge, Driver heuristic (full-charge and overlap-only), diesel proxy.

Paper instance set: 43 tests in `instances/PAPER_INSTANCE_SET_43.txt`. The two generated folders
`short_cl2_cu2_Balanced` and `short_cl2_cu2_Unbalanced` are not in the paper.

Base EV configuration used for the saved computational archive: 750 kWh, 60 km CS spacing, 350 kW, 1.49 kWh/km.
Manuscript Table 5 also mentions 500 kWh / 50 km; that planned grid is not the locked reviewer pack.

Generator provenance: `benchmark_v1` and the alternative generator dataset share names but differ in 147 files.
Use `benchmark_v1` for the paper instances.

Synchronization: time-overlap is the definition used in the reviewer pack.
