import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analysis import MAD_FLOOR, outliers  # noqa: E402
from model import build, metrics  # noqa: E402


def test_metrics_perfect_and_known_error():
    y = np.log(np.array([10.0, 20.0, 40.0]))
    m = metrics(y, y)
    assert m["rmse_log"] == 0 and m["r2_log"] == 1 and m["mape"] == 0
    m2 = metrics(y, y + np.log(2))  # always predicts double
    assert m2["rmse_log"] == pytest.approx(np.log(2))
    assert m2["median_ape"] == pytest.approx(1.0)


def test_build_features_shape_and_flags():
    d = pd.DataFrame({
        "strength_first": [10.0, np.nan, 5.0],
        "is_combo": [False, True, False],
        "n_ingredients": [1, 2, 1],
        "is_unbranded": [True, False, False],
        "n_competitors": [0, 3, 1],
        "n_competitors_same_form": [0, 2, 1],
        "dosage_group": ["tablet", "capsule", "tablet"],
    })
    X = build(d)
    assert X.strength_missing.tolist() == [0, 1, 0]
    assert X.is_unbranded.tolist() == [1, 0, 0]
    assert np.isnan(X.log_strength.iloc[1])
    assert X.filter(like="form_").shape[1] == 1  # drop_first leaves one dummy


def test_outlier_score_is_bounded_by_mad_floor():
    # five near-identical prices + one 2x: without the floor the z-score would explode
    prices = [100.0, 100.0, 100.0, 100.0, 100.0, 200.0]
    d = pd.DataFrame({
        "molecule": "m", "dosage_group": "tablet", "strength_first": 10.0,
        "is_combo": False, "strength_parse_ok": True, "price": prices,
        "log_price": np.log(prices), "trade_name": "t", "dosage_form": "f",
        "strength_raw": "10", "is_unbranded": False,
    })
    top, n = outliers(d)
    assert n == 6
    assert top.robust_z.abs().max() == pytest.approx(0.6745 * np.log(2) / MAD_FLOOR)


@pytest.mark.skipif(not (ROOT / "reports/model_results.json").exists(), reason="run model.py first")
def test_model_results_sane():
    import json
    r = json.loads((ROOT / "reports/model_results.json").read_text())
    for k in ["baseline_form_median_groupcv", "ols_groupcv", "lightgbm_groupcv"]:
        assert r[k]["rmse_log"] > 0
    assert r["n_molecules"] > 100
