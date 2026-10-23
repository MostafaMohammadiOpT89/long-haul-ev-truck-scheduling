import argparse
import csv
import math
import os
import shutil
import sys

# Wrapper around the original generator with solver-aligned constraints.
import instances.generator.main as tg


# -----------------------------
# Solver-aligned parameters
# -----------------------------
SPEED_KMPH = 60.0  # Match solver/network speed

CONSUMPTION_RATES = [1.12, 1.49, 2.08]
DISTANCES_PER_CS = [40, 50, 60, 70, 80, 90, 100]
BATTERY_CAPS = [750, 1000]
CPs = [350, 500, 1000]

# Global gap constraint to ensure feasibility across all testbed settings
MAX_GLOBAL_GAP_KM = 240.0
MAX_RESAMPLE_ATTEMPTS = 50
ADJUST_CUSTOMERS_FOR_GAP = True
USE_GLOBAL_SPACING_FOR_CUSTOMERS = True

# HOS limits from isFeasible.py
MAX_TIME_DRIVE_B = 4.5  # hours
MAX_TIME_DRIVE_R = 9.0  # hours
MAX_ELAPSED_B = 6.0     # hours
MAX_ELAPSED_R = 13.0    # hours
CS_SERVICE = 0.08       # hours, matches network CS service time


def validate_parameter_envelope() -> None:
    """Warn if any solver parameter combination is inherently infeasible."""
    max_consumption = max(CONSUMPTION_RATES)
    min_battery = min(BATTERY_CAPS)
    max_cs = max(DISTANCES_PER_CS)
    min_cs = min(DISTANCES_PER_CS)

    # Energy feasibility for CS segments
    max_leg_km_energy = min_battery / max_consumption
    if max_cs > max_leg_km_energy:
        print(
            f"WARNING: Max distance_per_cs ({max_cs} km) exceeds "
            f"energy-feasible leg length ({max_leg_km_energy:.1f} km) "
            "for worst-case battery/consumption."
        )

    # HOS feasibility for a single leg without break
    max_leg_km_hos = MAX_TIME_DRIVE_B * SPEED_KMPH
    if max_cs > max_leg_km_hos:
        print(
            f"WARNING: Max distance_per_cs ({max_cs} km) exceeds "
            f"HOS drive limit per break ({max_leg_km_hos:.1f} km)."
        )

    # Informational envelope
    print(
        "Generator envelope (worst-case): "
        f"battery={min_battery} kWh, consumption={max_consumption} kWh/km, "
        f"speed={SPEED_KMPH} km/h, max_cs={max_cs} km, min_cs={min_cs} km"
    )


def _read_distance_matrix(csv_path: str):
    """Read a distance matrix CSV and return (header, matrix)."""
    with open(csv_path, "r", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        return [], []
    header = rows[0][1:]  # first row: ["", node1, node2, ...]
    matrix = []
    for row in rows[1:]:
        if len(row) <= 1:
            continue
        matrix.append([float(x) for x in row[1:]])
    return header, matrix


def _read_instance_order(instance_path: str):
    """Read instance file and return ordered location names."""
    order = []
    with open(instance_path, "r", newline="") as f:
        reader = csv.reader(f)
        section = None
        is_first_vehicle = True
        for row in reader:
            if not row:
                continue
            if row[0].startswith("VehicleId"):
                section = "vehicles"
                continue
            if row[0].startswith("NodeId"):
                section = "nodes"
                continue
            if section == "vehicles" and is_first_vehicle:
                # vehicle_id, location, location_id
                if len(row) >= 2:
                    order.append(row[1])  # Origin
                is_first_vehicle = False
            elif section == "nodes":
                if len(row) >= 2:
                    order.append(row[1])
    return order


def _max_leg_distance_km(instance_path: str, dist_matrix_path: str) -> float:
    """Compute maximum consecutive-leg distance for an instance."""
    order = _read_instance_order(instance_path)
    header, matrix = _read_distance_matrix(dist_matrix_path)
    if not order or not header or not matrix:
        return 0.0
    index = {name: i for i, name in enumerate(header)}
    max_leg = 0.0
    for a, b in zip(order, order[1:]):
        if a not in index or b not in index:
            continue
        i, j = index[a], index[b]
        max_leg = max(max_leg, matrix[i][j])
    return max_leg


def _total_route_distance_km(instance_path: str, dist_matrix_path: str) -> float:
    """Compute total route length along the instance order."""
    order = _read_instance_order(instance_path)
    header, matrix = _read_distance_matrix(dist_matrix_path)
    if not order or not header or not matrix:
        return 0.0
    index = {name: i for i, name in enumerate(header)}
    total = 0.0
    for a, b in zip(order, order[1:]):
        if a not in index or b not in index:
            continue
        i, j = index[a], index[b]
        total += matrix[i][j]
    return total


def _max_customer_gap_km(instance_path: str, dist_matrix_path: str) -> float:
    """Compute max gap between consecutive customers (exclude origin/destination)."""
    order = _read_instance_order(instance_path)
    if len(order) <= 2:
        return 0.0
    customers = order[1:-1]
    header, matrix = _read_distance_matrix(dist_matrix_path)
    if not customers or not header or not matrix:
        return 0.0
    index = {name: i for i, name in enumerate(header)}
    max_gap = 0.0
    for a, b in zip(customers, customers[1:]):
        if a not in index or b not in index:
            continue
        i, j = index[a], index[b]
        max_gap = max(max_gap, matrix[i][j])
    return max_gap


def check_instance_feasibility(instance_dir: str) -> None:
    """Check feasibility envelope for a generated instance folder."""
    instance_name = os.path.basename(instance_dir)
    instance_file = os.path.join(instance_dir, f"{instance_name}.txt")
    dist_file = os.path.join(instance_dir, f"{instance_name}_DistanceMatrix.csv")
    if not os.path.isfile(instance_file) or not os.path.isfile(dist_file):
        return

    max_consumption = max(CONSUMPTION_RATES)
    min_battery = min(BATTERY_CAPS)
    min_cp = min(CPs)

    # Customer-to-customer gap check (exclude origin/destination)
    max_gap = _max_customer_gap_km(instance_file, dist_file)
    if max_gap > MAX_GLOBAL_GAP_KM + 1e-6:
        print(
            f"WARNING: {instance_name} has max customer gap {max_gap:.1f} km "
            f"> {MAX_GLOBAL_GAP_KM:.1f} km."
        )

    # Detailed HOS + charging feasibility per CS spacing (worst-case consumption/CP)
    order = _read_instance_order(instance_file)
    header, matrix = _read_distance_matrix(dist_file)
    idx = {name: i for i, name in enumerate(header)}

    def segment_distances(total_dist: float, cs_spacing: float):
        # Mirror network._generateCS and _generateArcs behavior
        if total_dist <= 0:
            return []
        if total_dist > cs_spacing:
            num_cs = math.floor(total_dist / cs_spacing)
        else:
            num_cs = 1
        if num_cs == 1:
            half = total_dist / 2.0
            # Two segments: start->CS, CS->end
            return [half, half]
        segments = [cs_spacing] * num_cs
        remaining = total_dist - (cs_spacing * num_cs)
        if remaining > 0:
            segments.append(remaining)
        return segments

    def violates_hos(segments, cs_spacing):
        drive_r = drive_b = 0.0
        elapsed_r = elapsed_b = 0.0

        for i, dist in enumerate(segments):
            drive_time = dist / SPEED_KMPH
            # Insert rest/break before driving if needed
            if drive_r + drive_time > MAX_TIME_DRIVE_R or elapsed_r + drive_time > MAX_ELAPSED_R:
                if elapsed_r > MAX_ELAPSED_R:
                    return True
                # rest
                drive_r = 0.0
                drive_b = 0.0
                elapsed_r = 0.0
                elapsed_b = 0.0
            if drive_b + drive_time > MAX_TIME_DRIVE_B or elapsed_b + drive_time > MAX_ELAPSED_B:
                # break
                drive_b = 0.0
                elapsed_b = 0.0

            # drive segment
            drive_r += drive_time
            drive_b += drive_time
            elapsed_r += drive_time
            elapsed_b += drive_time

            if drive_r > MAX_TIME_DRIVE_R or drive_b > MAX_TIME_DRIVE_B:
                return True
            if elapsed_r > MAX_ELAPSED_R or elapsed_b > MAX_ELAPSED_B:
                return True

            # if segment ends at CS (all but last), add service + charge time
            if i < len(segments) - 1:
                service_time = 0.08  # hours at CS
                charge_time = (dist * max_consumption) / min_cp
                elapsed_r += service_time + charge_time
                elapsed_b += service_time + charge_time
                if elapsed_r > MAX_ELAPSED_R or elapsed_b > MAX_ELAPSED_B:
                    return True
        return False

    for cs in DISTANCES_PER_CS:
        if not order or not header:
            break
        infeasible = False
        for a, b in zip(order, order[1:]):
            if a not in idx or b not in idx:
                continue
            total_dist = matrix[idx[a]][idx[b]]
            segs = segment_distances(total_dist, cs)
            if violates_hos(segs, cs):
                infeasible = True
                break
        if infeasible:
            print(
                f"WARNING: {instance_name} may be infeasible for CS spacing {cs} km "
                f"under worst-case consumption {max_consumption} and CP {min_cp}."
            )


def is_instance_feasible_worst_case(instance_file: str, dist_file: str) -> bool:
    """Return True if instance passes both max-leg and elapsed-based checks for all CS spacings."""
    max_consumption = max(CONSUMPTION_RATES)
    min_cp = min(CPs)

    order = _read_instance_order(instance_file)
    header, matrix = _read_distance_matrix(dist_file)
    if not order or not header or not matrix:
        return False
    idx = {name: i for i, name in enumerate(header)}

    def segment_distances(total_dist: float, cs_spacing: float):
        if total_dist <= 0:
            return []
        if total_dist > cs_spacing:
            num_cs = math.floor(total_dist / cs_spacing)
        else:
            num_cs = 1
        if num_cs == 1:
            half = total_dist / 2.0
            return [half, half]
        segs = [cs_spacing] * num_cs
        rem = total_dist - (cs_spacing * num_cs)
        if rem > 0:
            segs.append(rem)
        return segs

    def violates_hos(segments):
        drive_r = drive_b = elapsed_r = elapsed_b = 0.0
        for i, dist in enumerate(segments):
            drive_time = dist / SPEED_KMPH
            # rest before driving if needed
            if drive_r + drive_time > MAX_TIME_DRIVE_R or elapsed_r + drive_time > MAX_ELAPSED_R:
                drive_r = drive_b = elapsed_r = elapsed_b = 0.0
            if drive_b + drive_time > MAX_TIME_DRIVE_B or elapsed_b + drive_time > MAX_ELAPSED_B:
                drive_b = 0.0
                elapsed_b = 0.0
            # drive
            drive_r += drive_time
            drive_b += drive_time
            elapsed_r += drive_time
            elapsed_b += drive_time
            if drive_r > MAX_TIME_DRIVE_R or drive_b > MAX_TIME_DRIVE_B:
                return True
            if elapsed_r > MAX_ELAPSED_R or elapsed_b > MAX_ELAPSED_B:
                return True
            # CS stop between segments
            if i < len(segments) - 1:
                charge_time = (dist * max_consumption) / min_cp
                elapsed_r += CS_SERVICE + charge_time
                elapsed_b += CS_SERVICE + charge_time
                if elapsed_r > MAX_ELAPSED_R or elapsed_b > MAX_ELAPSED_B:
                    return True
        return False

    for cs in DISTANCES_PER_CS:
        for a, b in zip(order, order[1:]):
            if a not in idx or b not in idx:
                continue
            total_dist = matrix[idx[a]][idx[b]]
            segs = segment_distances(total_dist, cs)
            if violates_hos(segs):
                return False
    return True


def patch_generator_speed() -> None:
    """Force the original generator to use solver-aligned speed."""
    tg.SPEED_KMPH = SPEED_KMPH


def patch_distance_ranges() -> None:
    """Override route distance ranges to ensure feasibility under HOS/charging."""
    def _class_distance_range_km(route_class: str):
        rc = route_class.lower()
        if rc in ("short", "s", "sh"):
            # Round-trip doubles the backbone length, so use half here
            return 250.0, 275.0
        if rc in ("med", "medium", "m"):
            return 500.0, 550.0
        if rc in ("long", "l"):
            return 750.0, 800.0
        raise ValueError(f"Unknown route class: {route_class}")

    tg.class_distance_range_km = _class_distance_range_km


_ORIGINAL_SAMPLE_TOTAL_DISTANCE = None
_D_TOTAL_OVERRIDE = None


def patch_total_distance_sampler() -> None:
    """Allow test_generator2 to override the sampled total distance."""
    global _ORIGINAL_SAMPLE_TOTAL_DISTANCE
    if _ORIGINAL_SAMPLE_TOTAL_DISTANCE is None:
        _ORIGINAL_SAMPLE_TOTAL_DISTANCE = tg.sample_total_distance_km

    def _sample_total_distance_km(route_class: str, rng):
        if _D_TOTAL_OVERRIDE is not None:
            return _D_TOTAL_OVERRIDE
        return _ORIGINAL_SAMPLE_TOTAL_DISTANCE(route_class, rng)

    tg.sample_total_distance_km = _sample_total_distance_km


def patch_global_customer_spacing() -> None:
    """Place customers with global spacing to guarantee max gap."""
    if not USE_GLOBAL_SPACING_FOR_CUSTOMERS:
        return

    def _place_customers_within_clusters(centers, alloc, d_total, rng):
        total_customers = sum(alloc)
        if total_customers <= 0:
            return [], []
        gap = d_total / (total_customers + 1)
        positions = [(i + 1) * gap for i in range(total_customers)]
        membership = []
        idx = 0
        for cl, count in enumerate(alloc):
            for _ in range(count):
                if idx >= total_customers:
                    break
                membership.append(cl)
                idx += 1
        while len(membership) < total_customers:
            membership.append(len(alloc) - 1 if alloc else 0)
        return positions, membership

    def _enforce_intra_cluster_spacing(positions, membership, centers, d_total, rng, **kwargs):
        return positions, membership

    tg.place_customers_within_clusters = _place_customers_within_clusters
    tg.enforce_intra_cluster_spacing = _enforce_intra_cluster_spacing


def adjust_customers_for_gap(spec: "tg.RouteSpec") -> "tg.RouteSpec":
    """Increase customer count if current spec cannot satisfy max backbone gap."""
    _, d_hi = tg.class_distance_range_km(spec.route_class)
    # Minimum customers needed to keep max gap <= MAX_GLOBAL_GAP_KM
    min_customers_needed = max(1, math.ceil(d_hi / MAX_GLOBAL_GAP_KM) - 1)
    if spec.total_customers >= min_customers_needed:
        return spec

    # Build adjusted spec with increased customers
    return tg.RouteSpec(
        route_class=spec.route_class,
        clusters=spec.clusters,
        total_customers=min_customers_needed,
        variant_idx=spec.variant_idx,
        customer_range=spec.customer_range,
        round_trip=spec.round_trip,
        add_baatsfjord_column=spec.add_baatsfjord_column,
        allocation_strategy=spec.allocation_strategy,
        variant_label=spec.variant_label,
    )


def _instance_paths(instance_dir: str):
    instance_name = os.path.basename(instance_dir)
    instance_file = os.path.join(instance_dir, f"{instance_name}.txt")
    dist_file = os.path.join(instance_dir, f"{instance_name}_DistanceMatrix.csv")
    return instance_name, instance_file, dist_file


def generate_instance_feasible(spec: "tg.RouteSpec", out_root: str, rng) -> str:
    """Generate an instance and resample until max global gap is feasible."""
    original_generate = generate_instance_feasible._original_generate  # type: ignore[attr-defined]
    last_dir = None
    if ADJUST_CUSTOMERS_FOR_GAP:
        spec = adjust_customers_for_gap(spec)

    # If max gap remains infeasible, increase customers deterministically and retry.
    customer_bumps = 0
    global _D_TOTAL_OVERRIDE
    while True:
        last_total = None
        last_max_gap = None
        last_reason = None
        if _ORIGINAL_SAMPLE_TOTAL_DISTANCE is not None:
            d_total = _ORIGINAL_SAMPLE_TOTAL_DISTANCE(spec.route_class, rng)
        else:
            d_total = tg.sample_total_distance_km(spec.route_class, rng)
        if USE_GLOBAL_SPACING_FOR_CUSTOMERS:
            min_customers_needed = max(1, math.ceil(d_total / MAX_GLOBAL_GAP_KM) - 1)
            if spec.total_customers < min_customers_needed:
                spec = tg.RouteSpec(
                    route_class=spec.route_class,
                    clusters=spec.clusters,
                    total_customers=min_customers_needed,
                    variant_idx=spec.variant_idx,
                    customer_range=spec.customer_range,
                    round_trip=spec.round_trip,
                    add_baatsfjord_column=spec.add_baatsfjord_column,
                    allocation_strategy=spec.allocation_strategy,
                    variant_label=spec.variant_label,
                )
        _D_TOTAL_OVERRIDE = d_total
        for attempt in range(1, MAX_RESAMPLE_ATTEMPTS + 1):
            out_dir = original_generate(spec, out_root, rng)
            last_dir = out_dir
            instance_name, instance_file, dist_file = _instance_paths(out_dir)
            if os.path.isfile(instance_file) and os.path.isfile(dist_file):
                max_gap = _max_customer_gap_km(instance_file, dist_file)
                last_max_gap = max_gap
                last_total = _total_route_distance_km(instance_file, dist_file)
                if max_gap > MAX_GLOBAL_GAP_KM + 1e-6:
                    last_reason = "max_gap"
                else:
                    if not is_instance_feasible_worst_case(instance_file, dist_file):
                        print(
                            f"WARNING: {instance_name} fails worst_case, but generated anyway "
                            f"(total_route_km={last_total:.1f}, max_gap_km={max_gap:.1f})."
                        )
                    total_dist = _total_route_distance_km(instance_file, dist_file)
                    print(
                        f"Instance {instance_name}: total_route_km={total_dist:.1f}, "
                        f"max_customer_gap_km={max_gap:.1f}"
                    )
                    _D_TOTAL_OVERRIDE = None
                    return out_dir
            # Not feasible: remove and resample
            try:
                shutil.rmtree(out_dir)
            except Exception:
                pass
            if attempt % 10 == 0:
                reason = last_reason or "unknown"
                print(
                    f"Resampling {instance_name}: attempt {attempt} (reason={reason}, "
                    f"total_route_km={last_total:.1f} max_gap_km={last_max_gap:.1f})"
                    if last_total is not None and last_max_gap is not None
                    else f"Resampling {instance_name}: attempt {attempt} (reason={reason})"
                )

        # At this point, resampling failed: increase customers and retry
        if last_reason == "max_gap":
            customer_bumps += 1
            if customer_bumps > 5:
                print(f"WARNING: {spec} still exceeds max gap after customer bumps.")
                _D_TOTAL_OVERRIDE = None
                return last_dir
            if last_total is not None and last_max_gap is not None:
                print(
                    f"Last attempt for {spec}: total_route_km={last_total:.1f}, "
                    f"max_customer_gap_km={last_max_gap:.1f}"
                )
            spec = tg.RouteSpec(
                route_class=spec.route_class,
                clusters=spec.clusters,
                total_customers=spec.total_customers + 1,
                variant_idx=spec.variant_idx,
                customer_range=spec.customer_range,
                round_trip=spec.round_trip,
                add_baatsfjord_column=spec.add_baatsfjord_column,
                allocation_strategy=spec.allocation_strategy,
                variant_label=spec.variant_label,
            )
            print(f"Increasing customers for feasibility: {spec}")


def parse_args() -> argparse.Namespace:
    """Proxy to original generator args for compatibility."""
    return tg.parse_args()


def main() -> None:
    # Apply solver-aligned speed before any generation
    patch_generator_speed()
    patch_distance_ranges()
    patch_total_distance_sampler()
    patch_global_customer_spacing()
    validate_parameter_envelope()

    # Override generator to enforce global gap feasibility
    generate_instance_feasible._original_generate = tg.generate_instance  # type: ignore[attr-defined]
    tg.generate_instance = generate_instance_feasible

    # Delegate to original generator logic so test set stays identical
    args = parse_args()
    if args.cmd == "generate":
        out_dir = tg.run_generate(args)
        if out_dir:
            check_instance_feasibility(out_dir)
        return
    if args.cmd == "grid":
        tg.run_grid(args)
        # Check all instances in output directory
        if getattr(args, "out", None):
            for name in os.listdir(args.out):
                path = os.path.join(args.out, name)
                if os.path.isdir(path):
                    check_instance_feasibility(path)
        return
    if args.cmd == "master":
        tg.run_master(args)
        return
    if args.demo or args.cmd is None:
        tg.run_demo(args)
        if getattr(args, "out", None):
            for name in os.listdir(args.out):
                path = os.path.join(args.out, name)
                if os.path.isdir(path):
                    check_instance_feasibility(path)
        return


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)
