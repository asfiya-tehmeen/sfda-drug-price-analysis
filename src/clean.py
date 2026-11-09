"""Clean the parsed SFDA list table.

Input : data/clean/list_raw_parsed.csv   (from parse.py, raw strings)
Output: data/clean/products_clean.parquet
        reports/data_quality.csv         (rows in/out, drops per reason, parse rates)

Rules (documented in reports/REPORT.md later):
  1. Drop repeated rows with the same register_no (keep first). The site's paging
     repeats rows across page boundaries.
  2. Drop price <= 0.
  3. Lower-case and whitespace-normalise names; strip trailing '*' from trade names.
  4. Combination = comma in scientific name. Ingredient order is kept so it stays
     aligned with strength values.
  5. Strength is parsed ONLY when it is a plain list of numbers ("10,5" or "0.9").
     Anything else (ranges, 10^x, text, missing) keeps strength_raw, gets
     strength_parse_ok=False and is never guessed. The list has no strength unit.
  6. Advanced therapies (gene / cell therapies) are flagged, not dropped, and are
     modelled separately.
"""
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
IN_PATH = ROOT / "data" / "clean" / "list_raw_parsed.csv"
OUT_PATH = ROOT / "data" / "clean" / "products_clean.parquet"
DQ_PATH = ROOT / "reports" / "data_quality.csv"

_NUM = r"\d+(?:\.\d+)?"
STRENGTH_RE = re.compile(rf"^{_NUM}(?:\s*,\s*{_NUM})*$")

# Gene / cell therapy markers in the (lower-cased) scientific name.
ADVANCED_RE = re.compile(r"leucel|temcel|parvovec|tagene|\bgene\b|\w+vec\b|\w+cel\b")

DOSAGE_GROUPS = [  # first match wins, so order matters
    ("injection_infusion", r"inject|infusion|intravenous|parenteral"),
    ("ophthalmic", r"eye|ophthalm|intraocular"),
    ("tablet", r"tablet|caplet|lozenge"),
    ("capsule", r"capsule"),
    ("inhaled_nasal", r"inhal|nasal|spray|aerosol|nebul"),
    ("topical", r"cream|ointment|gel|lotion|topical|cutaneous|patch|plaster|shampoo|paste"),
    ("oral_liquid", r"oral|syrup|suspension|solution|drops|sachet|granules|powder"),
]


def normalise_name(s: pd.Series) -> pd.Series:
    return s.fillna("").str.lower().str.replace(r"\s+", " ", regex=True).str.strip()


def parse_strength(raw) -> tuple[list[float] | None, bool]:
    """Return (values, ok). ok is False for missing or non-plain-numeric strengths."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None, False
    s = re.sub(r"\s+", " ", str(raw)).strip()
    if not STRENGTH_RE.match(s):
        return None, False
    return [float(x) for x in re.split(r"\s*,\s*", s)], True


def dosage_group(form: str) -> str:
    f = (form or "").lower()
    for group, pattern in DOSAGE_GROUPS:
        if re.search(pattern, f):
            return group
    return "other"


def is_advanced_therapy(sci_name_lower: str) -> bool:
    return bool(ADVANCED_RE.search(sci_name_lower))


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    dq = [("rows_in", len(df))]
    d = df.copy()

    n = len(d)
    d = d.drop_duplicates("register_no", keep="first")
    dq.append(("dropped_duplicate_register_no", n - len(d)))

    d["price"] = pd.to_numeric(d["price"], errors="coerce")
    n = len(d)
    d = d[d["price"] > 0]
    dq.append(("dropped_price_missing_or_nonpositive", n - len(d)))

    d["scientific_name_raw"] = d["scientific_name"]
    d["scientific_name"] = normalise_name(d["scientific_name"])
    d["trade_name"] = (
        d["trade_name"].fillna("").str.replace(r"\*+\s*$", "", regex=True)
        .str.replace(r"\s+", " ", regex=True).str.strip()
    )
    d["strength_raw"] = d["strength"]
    d["dosage_form"] = d["dosage_form"].fillna("").str.strip()

    d["ingredients"] = d["scientific_name"].apply(
        lambda s: [x.strip() for x in s.split(",") if x.strip()]
    )
    d["n_ingredients"] = d["ingredients"].str.len()
    d["is_combo"] = d["n_ingredients"] > 1

    parsed = d["strength_raw"].apply(parse_strength)
    d["strength_values"] = parsed.str[0]
    d["strength_parse_ok"] = parsed.str[1]
    d["strength_matches_ingredients"] = d.apply(
        lambda r: bool(r["strength_parse_ok"]) and len(r["strength_values"]) == r["n_ingredients"],
        axis=1,
    )
    d["strength_first"] = d["strength_values"].apply(lambda v: v[0] if v else float("nan"))

    d["dosage_group"] = d["dosage_form"].apply(dosage_group)
    d["is_advanced_therapy"] = d["scientific_name"].apply(is_advanced_therapy)
    d["log_price"] = d["price"].apply(lambda p: __import__("math").log(p))

    d = d.drop(columns=["strength", "page"]).reset_index(drop=True)

    dq.append(("rows_out", len(d)))
    dq.append(("parse_ok_strength_pct", round(100 * d["strength_parse_ok"].mean(), 1)))
    dq.append(("strength_matches_ingredients_pct", round(100 * d["strength_matches_ingredients"].mean(), 1)))
    dq.append(("combination_products", int(d["is_combo"].sum())))
    dq.append(("advanced_therapies_flagged", int(d["is_advanced_therapy"].sum())))
    dq.append(("dosage_group_other", int((d["dosage_group"] == "other").sum())))
    return d, pd.DataFrame(dq, columns=["metric", "value"])


if __name__ == "__main__":
    out, dq = clean(pd.read_csv(IN_PATH, dtype=str))
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DQ_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT_PATH, index=False)
    dq.to_csv(DQ_PATH, index=False)
    print(dq.to_string(index=False))
    print(f"\nwrote {OUT_PATH}")
