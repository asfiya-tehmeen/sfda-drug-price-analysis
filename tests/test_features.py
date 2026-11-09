import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from features import add_features, is_unbranded  # noqa: E402


def test_unbranded_rule():
    assert is_unbranded("ABIRATERONE SPC 250MG F.C.TABLET", ["abiraterone acetate"])
    assert is_unbranded("0.9% W/V SODIUM CHLORIDE B.P", ["sodium chloride"])
    assert not is_unbranded("ORENCIA 250MG POWDER", ["abatacept"])
    assert not is_unbranded("CADUET 5-10", ["atorvastatin calcium", "amlodipine besilate"])
    assert not is_unbranded("X", [])


def test_competitor_counts():
    d = pd.DataFrame({
        "register_no": ["1", "2", "3"],
        "scientific_name": ["a", "a", "b"],
        "trade_name": ["A 10MG", "BRANDX", "B"],
        "ingredients": [["a"], ["a"], ["b"]],
        "dosage_group": ["tablet", "tablet", "tablet"],
    })
    out = add_features(d)
    assert out.n_competitors.tolist() == [1, 1, 0]
    assert out.n_competitors_same_form.tolist() == [1, 1, 0]
