"""Extract observed dish sales from Taigel's public Mendeley CSV archive."""

from __future__ import annotations

import argparse
import csv
import io
import zipfile
from datetime import datetime
from pathlib import Path


DISHES = ("CALAMARI", "FISCH", "GARNELEN", "HAEHNCHEN", "KOEFTE", "LAMM", "STEAK")


def prepare(source_zip: Path, output: Path) -> int:
    rows = []
    with zipfile.ZipFile(source_zip) as archive:
        with archive.open("data_preprocessed.csv") as source:
            reader = csv.DictReader(io.TextIOWrapper(source, encoding="utf-8-sig"), delimiter=";")
            if not {"DEMAND_DATE", *DISHES}.issubset(reader.fieldnames or []):
                raise ValueError("Unexpected source columns")
            for record in reader:
                day = datetime.strptime(record["DEMAND_DATE"], "%m.%d.%Y").date()
                for dish in DISHES:
                    sold = int(record[dish])
                    if sold < 0:
                        raise ValueError(f"Negative demand for {dish} on {day}")
                    rows.append((day.isoformat(), dish, sold))
    if len({(day, dish) for day, dish, _ in rows}) != len(rows):
        raise ValueError("Duplicate date and dish")
    rows.sort()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as target:
        writer = csv.writer(target)
        writer.writerow(("date", "dish", "sold"))
        writer.writerows(rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_zip", type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "data" / "restaurant_dish_sales.csv")
    args = parser.parse_args()
    print(f"Wrote {prepare(args.source_zip, args.output)} dish-day records to {args.output}")


if __name__ == "__main__":
    main()
