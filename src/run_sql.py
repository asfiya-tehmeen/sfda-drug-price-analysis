"""Run the DuckDB SQL layer: cleaning, data-quality counts and analyst views.

Input : data/clean/list_raw_parsed.csv   (from parse.py)
Output: data/clean/sfda.duckdb           (local database, not committed)
        reports/sql/*.csv                (views exported for review)

Run from the project root:  python src/run_sql.py
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql"
DB_PATH = ROOT / "data" / "clean" / "sfda.duckdb"
OUT_DIR = ROOT / "reports" / "sql"
POWERBI_DIR = ROOT / "powerbi" / "data"

# file name -> table or view to export
EXPORTS = {
    "data_quality": "data_quality",
    "dosage_group_summary": "v_dosage_group_summary",
    "competition_by_molecule": "v_competition_by_molecule",
    "ratio_cells": "v_ratio_cells",
    "ratio_summary": "v_ratio_summary",
}

# Aggregate-only extracts for the Power BI dashboard (sql/04_powerbi_extracts.sql)
POWERBI_EXPORTS = {
    "form_summary": "v_pbi_form_summary",
    "form_brandtype": "v_pbi_form_brandtype",
    "competition_distribution": "v_pbi_competition_distribution",
    "competition_by_molecule": "v_pbi_competition_by_molecule",
    "ratio_cells": "v_pbi_ratio_cells",
    "headline": "v_pbi_headline",
    "data_quality": "data_quality",
}


def run(db_path: Path = DB_PATH, out_dir: Path = OUT_DIR,
        powerbi_dir: Path = POWERBI_DIR) -> duckdb.DuckDBPyConnection:
    """Run sql/NN_*.sql in order, export the results, and return the open connection."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    powerbi_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    # the SQL files use paths relative to the project root
    con.execute(f"SET file_search_path = '{ROOT.as_posix()}'")
    for sql_file in sorted(SQL_DIR.glob("[0-9][0-9]_*.sql")):
        con.execute(sql_file.read_text(encoding="utf-8"))
    for name, relation in EXPORTS.items():
        target = (out_dir / f"{name}.csv").as_posix()
        con.execute(f"COPY (SELECT * FROM {relation}) TO '{target}' (HEADER, DELIMITER ',')")
    for name, relation in POWERBI_EXPORTS.items():
        target = (powerbi_dir / f"{name}.csv").as_posix()
        con.execute(f"COPY (SELECT * FROM {relation}) TO '{target}' (HEADER, DELIMITER ',')")
    return con


if __name__ == "__main__":
    con = run()
    print(con.execute("SELECT * FROM data_quality").df().to_string(index=False))
    print()
    print(con.execute("SELECT * FROM v_ratio_summary").df().to_string(index=False))
    con.close()
    print(f"\nwrote {DB_PATH}, CSVs in {OUT_DIR} and Power BI extracts in {POWERBI_DIR}")
