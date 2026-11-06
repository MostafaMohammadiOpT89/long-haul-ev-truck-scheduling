"""Paper summary scope: ten one-at-a-time settings and diesel references."""
import csv

PARAMETERS = ("battery_kwh", "charging_power_kw", "station_spacing_km", "consumption_kwh_per_km")
BASE = (750., 350., 60., 1.49)
SENSITIVITIES = ((350., 500., 1000.), (1000.,), (40., 80., 100.), (1.12, 2.08))


def configurations():
    settings = [BASE]
    for index, values in enumerate(SENSITIVITIES):
        for value in values:
            setting = list(BASE)
            setting[index] = value
            settings.append(tuple(setting))
    return settings


def parameter_tuple(row):
    return tuple(float(row[k]) for k in PARAMETERS)


def in_scope(row, paper_ids):
    return row["instance_id"] in paper_ids and (
        row["vehicle_type"] == "diesel_proxy" or parameter_tuple(row) in configurations())


def write_csv(path, fields, rows):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def write_summary_views(summaries, destination, paper_ids):
    """Keep the full catalog available; expose only the requested paper scope."""
    scoped = [row for row in summaries if in_scope(row, paper_ids)]
    fields = list(summaries[0])
    write_csv(destination / "summary_all.csv", fields, summaries)
    write_csv(destination / "summary.csv", fields, scoped)
    coverage, missing_runs = [], []
    partial = [row for row in scoped if row["policy"] == "partial_labeling"
               and row["vehicle_type"] == "electric"]
    for values in configurations():
        config = dict(zip(PARAMETERS, values))
        rows = [r for r in partial if parameter_tuple(r) == values]
        available = {r["instance_id"] for r in rows if r["record_status"] == "record_available"}
        missing = sorted(paper_ids - available)
        coverage.append(dict(**config, expected_instances=len(paper_ids),
                             available_instances=len(available), missing_instances=len(missing)))
        for instance in missing:
            missing_runs.append(dict(instance_id=instance, policy="partial_labeling",
                                     charging_policy="partial", **config,
                                     record_status="no_record_available"))
    write_csv(destination / "one_at_a_time_coverage.csv", list(coverage[0]), coverage)
    missing_fields = ["instance_id", "policy", "charging_policy", *PARAMETERS, "record_status"]
    write_csv(destination / "missing_partial_runs.csv", missing_fields, missing_runs)
    return dict(
        summary_scope="43 paper instances; base and one-at-a-time EV settings; diesel references; all policies retained",
        paper_base=dict(zip(PARAMETERS, BASE)),
        one_at_a_time_configurations=[dict(zip(PARAMETERS, x)) for x in configurations()],
        summary_row_count=len(scoped),
        summary_records_available=sum(r["record_status"] == "record_available" for r in scoped),
        summary_records_missing=sum(r["record_status"] == "no_record_available" for r in scoped),
        missing_partial_runs=len(missing_runs),
    )
