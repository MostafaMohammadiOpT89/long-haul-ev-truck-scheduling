"""Load matrices from an instance's own dataset, independent of the current directory."""
from pathlib import Path
from common import arcs, csv_reader


def load_city_arcs(instance_path):
    instance = Path(instance_path).resolve()
    distance = instance.with_name(instance.stem + "_DistanceMatrix.csv")
    travel_time = instance.with_name(instance.stem + "_TimeMatrix.csv")
    if not distance.is_file() or not travel_time.is_file():
        distance = instance.parent.parent / "Master_DistanceMatrix.csv"
        travel_time = instance.parent.parent / "Master_TimeMatrix.csv"
    if not distance.is_file() or not travel_time.is_file():
        raise FileNotFoundError(f"Missing instance and dataset master matrices for {instance}")
    return arcs.cityArcs.createArcs(csv_reader.CSVreader(str(distance)), csv_reader.CSVreader(str(travel_time)))
