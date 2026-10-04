"""Transactional CSV import/export for the sea-level SQLite database."""
import argparse
import csv
import os
import sqlite3
from pathlib import Path


TABLES = {
    "tide_gauges", "tide_gauge_measurements", "satellites",
    "satellite_measurements", "risk_zones", "storm_surges", "users",
    "api_access_log",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("direction", choices=("export", "import"))
    parser.add_argument("table", choices=sorted(TABLES))
    parser.add_argument("file", type=Path)
    parser.add_argument("--database", default=os.getenv("SQLITE_PATH", "sea_level.db"))
    args = parser.parse_args()

    connection = sqlite3.connect(args.database)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{args.table}")')]
        if not columns:
            raise SystemExit(f"Table {args.table} does not exist in {args.database}")
        if args.direction == "export":
            with args.file.open("w", newline="", encoding="utf-8-sig") as output:
                writer = csv.writer(output, lineterminator="\n")
                writer.writerow(columns)
                writer.writerows(connection.execute(f'SELECT * FROM "{args.table}"'))
            print(f"Exported {connection.execute(f'SELECT count(*) FROM "{args.table}"').fetchone()[0]} rows")
        else:
            with args.file.open("r", newline="", encoding="utf-8-sig") as source:
                reader = csv.DictReader(source)
                if reader.fieldnames != columns:
                    raise SystemExit("CSV header must match database columns in exact order: " + ", ".join(columns))
                placeholders = ",".join("?" for _ in columns)
                statement = f'INSERT INTO "{args.table}" ({",".join(columns)}) VALUES ({placeholders})'
                batch = [tuple(row[column] if row[column] != "" else None for column in columns) for row in reader]
            with connection:
                connection.executemany(statement, batch)
            print(f"Imported {len(batch)} rows")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
