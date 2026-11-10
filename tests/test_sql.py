"""Reconcile the DuckDB SQL layer with the pandas pipeline.

Both sides start from the same parsed file (data/clean/list_raw_parsed.csv). The
tests compare row counts, drop counts, per-row flags, the ratio cells and the
headline median ratio. Skipped when the data is not present (data/ is not committed).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

duckdb = pytest.importorskip("duckdb")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analysis import CELL, ratio_cells  # noqa: E402
from clean import clean  # noqa: E402
from features import add_features  # noqa: E402
from run_sql import run  # noqa: E402

PARSED = ROOT / "data" / "clean" / "list_raw_parsed.csv"
pytestmark = pytest.mark.skipif(not PARSED.exists(), reason="parsed data not present (run parse.py)")


@pytest.fixture(scope="module")
def sql(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("sql")
    con = run(db_path=tmp / "test.duckdb", out_dir=tmp / "out", powerbi_dir=tmp / "pbi")
    yield {
        "con": con,
        "dq": con.execute("SELECT * FROM data_quality").df().set_index("metric")["value"],
        "products": con.execute("SELECT * FROM products_features").df(),
        "cells": con.execute("SELECT * FROM v_ratio_cells").df(),
        "summary": con.execute("SELECT * FROM v_ratio_summary").df().iloc[0],
        "out": tmp / "out",
        "pbi": tmp / "pbi",
    }
    con.close()


@pytest.fixture(scope="module")
def pandas_side():
    cleaned, dq = clean(pd.read_csv(PARSED, dtype=str))
    feats = add_features(cleaned)
    cells = ratio_cells(feats[~feats.is_advanced_therapy])
    return {"dq": dq.set_index("metric")["value"], "products": feats, "cells": cells}


def test_data_quality_counts_match(sql, pandas_side):
    assert list(sql["dq"].index) == list(pandas_side["dq"].index)
    for metric, expected in pandas_side["dq"].items():
        tol = 0.051 if metric.endswith("_pct") else 0  # percentages are rounded to 1 dp
        assert sql["dq"][metric] == pytest.approx(expected, abs=tol), metric
    # the key counts are exact, not approximate
    for metric in ["rows_in", "dropped_duplicate_register_no",
                   "dropped_price_missing_or_nonpositive", "rows_out"]:
        assert sql["dq"][metric] == pandas_side["dq"][metric], metric


def test_data_quality_matches_committed_report(sql):
    report = ROOT / "reports" / "data_quality.csv"
    if not report.exists():
        pytest.skip("reports/data_quality.csv not present")
    committed = pd.read_csv(report).set_index("metric")["value"]
    for metric, expected in committed.items():
        tol = 0.051 if metric.endswith("_pct") else 0
        assert sql["dq"][metric] == pytest.approx(expected, abs=tol), metric


def test_same_rows_and_row_level_flags(sql, pandas_side):
    s = sql["products"].set_index("register_no").sort_index()
    p = pandas_side["products"].set_index("register_no").sort_index()
    assert list(s.index) == list(p.index)
    for col in ["molecule", "trade_name", "dosage_group", "n_ingredients", "n_competitors",
                "n_competitors_same_form"]:
        assert (s[col].to_numpy() == p[col].to_numpy()).all(), col
    for col in ["is_combo", "is_advanced_therapy", "strength_parse_ok", "is_unbranded",
                "strength_matches_ingredients"]:
        assert (s[col].astype(bool).to_numpy() == p[col].astype(bool).to_numpy()).all(), col
    assert np.allclose(s["price"], p["price"], rtol=0, atol=0)
    assert np.allclose(s["strength_first"], p["strength_first"], equal_nan=True, rtol=1e-12)


def test_ratio_cells_match(sql, pandas_side):
    s, p = sql["cells"], pandas_side["cells"]
    assert len(s) == len(p)
    stats_file = ROOT / "reports" / "stats_results.json"
    if stats_file.exists():
        assert len(s) == json.loads(stats_file.read_text())["n_cells"] == 247
    merged = p.merge(s, on=CELL, suffixes=("_pd", "_sql"), how="outer", indicator=True)
    assert (merged["_merge"] == "both").all()
    assert np.allclose(merged["ratio_pd"], merged["ratio_sql"], rtol=1e-12)
    assert (merged["n_unbranded_pd"] == merged["n_unbranded_sql"]).all()
    assert (merged["n_brand_pd"] == merged["n_brand_sql"]).all()
    assert np.allclose(merged["n_competitors_same_form_pd"], merged["n_competitors_same_form_sql"])


def test_median_ratio_matches(sql, pandas_side):
    pandas_median = float(np.exp(np.median(np.log(pandas_side["cells"]["ratio"]))))
    assert sql["summary"]["median_ratio_unbranded_to_brand"] == pytest.approx(pandas_median, rel=1e-12)
    assert sql["summary"]["n_cells"] == len(pandas_side["cells"])
    stats_file = ROOT / "reports" / "stats_results.json"
    if stats_file.exists():
        reported = json.loads(stats_file.read_text())
        assert sql["summary"]["median_ratio_unbranded_to_brand"] == pytest.approx(
            reported["median_ratio_unbranded_to_brand"], rel=1e-9)
        assert sql["summary"]["share_cells_unbranded_cheaper"] == pytest.approx(
            reported["share_cells_unbranded_cheaper"], rel=1e-9)


def test_views_export_and_are_not_empty(sql):
    con = sql["con"]
    assert con.execute("SELECT count(*) FROM v_dosage_group_summary").fetchone()[0] >= 5
    # shares of products by dosage group add up to ~100%
    total = con.execute("SELECT sum(pct_of_products) FROM v_dosage_group_summary").fetchone()[0]
    assert total == pytest.approx(100, abs=0.5)
    # competition: rank 1 is the molecule with the most registrations
    top = con.execute("SELECT n_registrations FROM v_competition_by_molecule WHERE competition_rank = 1").fetchall()
    assert max(r[0] for r in top) == con.execute(
        "SELECT max(n_registrations) FROM v_competition_by_molecule").fetchone()[0]
    for name in ["data_quality", "dosage_group_summary", "competition_by_molecule",
                 "ratio_cells", "ratio_summary"]:
        assert (sql["out"] / f"{name}.csv").exists(), name


def test_powerbi_extracts_are_aggregate_only_and_consistent(sql):
    pbi = sql["pbi"]
    files = ["form_summary", "form_brandtype", "competition_distribution",
             "competition_by_molecule", "ratio_cells", "headline", "data_quality"]
    frames = {n: pd.read_csv(pbi / f"{n}.csv") for n in files}

    # no row-level price columns in the cell-level extract
    assert not any("price" in c for c in frames["ratio_cells"].columns)
    # medians and quartiles are blank for groups of fewer than 3 products
    fb = frames["form_brandtype"]
    small = fb[fb.n_products < 3]
    assert small[["median_price", "p25_price", "p75_price"]].isna().all().all()
    assert fb[fb.n_products >= 3]["median_price"].notna().all()
    cm = frames["competition_by_molecule"]
    assert cm[cm.n_registrations < 3]["median_price"].isna().all()

    # consistency with the main SQL results
    h = frames["headline"].iloc[0]
    assert h["n_cells"] == len(frames["ratio_cells"]) == sql["summary"]["n_cells"]
    assert h["n_products_cleaned"] == sql["dq"]["rows_out"]
    assert h["n_products_in_analysis"] + h["n_advanced_therapies_excluded"] == h["n_products_cleaned"]
    assert frames["form_summary"]["n_products"].sum() == h["n_products_in_analysis"]
    assert fb["n_products"].sum() == h["n_products_in_analysis"]
    assert frames["competition_by_molecule"]["n_registrations"].sum() == h["n_products_in_analysis"]
    dist = frames["competition_distribution"]
    assert dist["n_molecules"].sum() == len(cm)
