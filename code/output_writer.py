"""
FinCredTwin Output Writer
CSV serialization adhering to the official output contract.

Derives row count dynamically from requests — never hardcoded.
"""
import csv
from typing import Dict, List

from config import OUTPUT_COLUMNS, OUTPUT_CSV, ROOT_OUTPUT_CSV


def write_output(rows: List[Dict[str, str]], output_path=None) -> None:
    """
    Write output rows to CSV with exact column order.
    Writes to both dataset/output.csv and root output.csv for maximum compatibility.
    """
    primary_path = output_path or OUTPUT_CSV
    paths = [primary_path]
    if output_path is None and ROOT_OUTPUT_CSV != primary_path:
        paths.append(ROOT_OUTPUT_CSV)
    
    for path in paths:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            for row in rows:
                clean_row = {col: row.get(col, "") for col in OUTPUT_COLUMNS}
                writer.writerow(clean_row)

