# Sensitivity tables (Full vs Partial vs diesel)

n refers to feasible instance × config pairs, not always 43.

EV grid: consumption `{1.12, 1.49, 2.08}` × spacing `{40, 60, 80, 100}` km × battery `{750, 1000}` kWh × power `{350, 500, 1000}` kW.

| File group | Content |
|---|---|
| `table_sensitivity_*.csv` | Partial vs Full at identical EV settings |
| `table_ev_vs_diesel_*.csv` | EV vs diesel proxy |
| `table_charging_sync.csv` | One row per (instance, strategy, config) |
