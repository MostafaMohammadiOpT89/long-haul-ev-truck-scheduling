# Main generator and frozen benchmark

`instances/benchmark_v1/` is the authoritative set of 45 instances used by the
route/corridor visualization. Its 227 files are unchanged.

The main generator is `instances/generator/main.py`, formerly `Test_Generator.py`.
Run it from the repository root:

```sh
python -m instances.generator grid --seed 42 --add-unbalanced-variant --out output/generated_instances
```

It retains the original clustered-route design: short routes 800–1200 km,
medium routes 1500–2500 km, long routes 3000–4000 km, and travel speed 60 km/h.
Generated inputs are new datasets, not replacements for the frozen benchmark.

Before the reproducibility fix, a seed-42 grid with unbalanced variants produced
227 files: 187 matched the benchmark byte for byte, including all 45 instance
TXT files and both master matrices. The remaining 40 files were diagnostics,
summaries, distance matrices and time matrices for 10 instances. The spacing
function used global `random.uniform` and `random.random`, ignoring its supplied
seeded RNG. Those calls now use that RNG. This makes new seeded runs repeatable,
but also changes the subsequent random sequence; the original unseeded state
cannot be recovered from seed 42.

For an exact copy of the historical mapped dataset, use its checked catalog:

```sh
python -m instances.materialize benchmark_v1 output/benchmark_copy
```

The alternative generator is archived as `legacy/generators/solver_aligned.py`
(formerly `test_generator2.py`). It changes route ranges to 250–275, 500–550 and
750–800 km, uses global customer spacing, and adjusts/resamples customer counts
for gap feasibility. Its comparison run produced 222 files with no byte-identical
benchmark matches. It is not the generator to use for the mapped benchmark design.

The alternative saved dataset is archived separately at
`legacy/instances/alternative_generator_output/`. Its catalog ID is
`legacy_generator_variant`. Only its 147 differing files are stored there;
80 shared files still refer to the benchmark through the catalog. This saved
dataset is not asserted to be the output of the archived generator version.
