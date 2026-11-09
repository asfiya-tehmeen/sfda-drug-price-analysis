import math
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from clean import (  # noqa: E402
    clean,
    dosage_group,
    is_advanced_therapy,
    parse_strength,
)


def make_df(rows):
    cols = ["scientific_name", "trade_name", "strength", "dosage_form", "price", "register_no", "page"]
    return pd.DataFrame(rows, columns=cols, dtype=str)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0.9", ([0.9], True)),
        ("10,5", ([10.0, 5.0], True)),
        ("120 , 2.5", ([120.0, 2.5], True)),
        (" 250 ", ([250.0], True)),
    ],
)
def test_parse_strength_ok(raw, expected):
    assert parse_strength(raw) == expected


@pytest.mark.parametrize(
    "raw", ["40-62.5", "1*10^13", "0.5 + 1", "nlt2.2*106", "15,10,4<,10", "", None, float("nan")]
)
def test_parse_strength_rejects_non_plain(raw):
    assert parse_strength(raw) == (None, False)


def test_dosage_groups():
    assert dosage_group("Film-coated tablet") == "tablet"
    assert dosage_group("Powder for solution for infusion") == "injection_infusion"
    assert dosage_group("Concentrate for solution for infusion") == "injection_infusion"
    assert dosage_group("Capsule, hard") == "capsule"
    assert dosage_group("Eye drops, solution") == "ophthalmic"
    assert dosage_group("Powder for oral solution in sachet") == "oral_liquid"
    assert dosage_group("Suppository") == "other"


@pytest.mark.parametrize(
    "name",
    ["atidarsagene autotemcel", "etranacogene dezaparvovec", "onasemnogene abeparvovec",
     "ciltacabtagene autoleucel", "tisagenlecleucel", "voretigene neparvovec",
     "lisocabtagene maraleucel", "exagamglogene autotemcel"],
)
def test_advanced_therapies_flagged(name):
    assert is_advanced_therapy(name)


@pytest.mark.parametrize(
    "name", ["sodium chloride", "atorvastatin calcium,amlodipine besilate", "nusinersen",
             "abatacept", "paracetamol", "insulin glargine"],
)
def test_conventional_drugs_not_flagged(name):
    assert not is_advanced_therapy(name)


def test_clean_rules_and_counts():
    df = make_df([
        ["SODIUM CHLORIDE", "SALINE*", "0.9", "Solution for injection", "0.75", "A1", "0"],
        ["SODIUM CHLORIDE", "SALINE*", "0.9", "Solution for injection", "0.75", "A1", "1"],  # repeat
        ["ATORVASTATIN CALCIUM,AMLODIPINE BESILATE", "CADUET 5-10", "10,5", "Tablet", "107.3", "B2", "0"],
        ["Live vaccine", "ACAM2000", "1-5", "Lyophilisate for solution for injection", "00", "C3", "0"],  # zero
        ["Tisagenlecleucel", "Kymriah", "6", "Dispersion for infusion", "1633500", "D4", "0"],
    ])
    out, dq = clean(df)
    m = dict(zip(dq.metric, dq.value))
    assert m["rows_in"] == 5
    assert m["dropped_duplicate_register_no"] == 1
    assert m["dropped_price_missing_or_nonpositive"] == 1
    assert m["rows_out"] == len(out) == 3
    assert out.register_no.is_unique
    assert (out.price > 0).all()
    assert not out.duplicated("register_no").any()

    cad = out[out.register_no == "B2"].iloc[0]
    assert cad.is_combo and cad.n_ingredients == 2 and cad.strength_matches_ingredients
    assert out[out.register_no == "A1"].iloc[0].trade_name == "SALINE"
    kym = out[out.register_no == "D4"].iloc[0]
    assert kym.is_advanced_therapy
    assert math.isclose(kym.log_price, math.log(1633500))


@pytest.mark.skipif(not (ROOT / "data/clean/products_clean.parquet").exists(), reason="run clean.py first")
def test_real_output_invariants():
    d = pd.read_parquet(ROOT / "data/clean/products_clean.parquet")
    assert d.register_no.is_unique
    assert (d.price > 0).all()
    assert d.dosage_group.notna().all()
    assert d.loc[d.strength_parse_ok, "strength_values"].apply(len).ge(1).all()
