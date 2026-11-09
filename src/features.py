"""Features: unbranded flag and competition counts.

Input : data/clean/products_clean.parquet
Output: data/clean/features.parquet
        reports/generic_flag_check.csv   (30 random rows for the hand-check)

UNBRANDED FLAG (documented, heuristic). This is NOT an originator/generic flag.
  is_unbranded = True when the lower-cased trade name contains the first word
  (>= 5 letters) of the first ingredient. e.g. "ABIRATERONE SPC 250MG F.C.TABLET"
  -> True, "ORENCIA 250MG ..." -> False.
  False means "brand-named", which mixes originators with branded generics
  (e.g. "LOVERA" for tadalafil). The list has no registration date, manufacturer
  or originator field to separate them, so the analysis compares unbranded vs
  brand-named only. Report the hand-check agreement next to every result that
  uses this flag.
"""
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
IN_PATH = ROOT / "data" / "clean" / "products_clean.parquet"
OUT_PATH = ROOT / "data" / "clean" / "features.parquet"
CHECK_PATH = ROOT / "reports" / "generic_flag_check.csv"


def first_stem(ingredients) -> str:
    if len(ingredients) == 0:
        return ""
    words = re.findall(r"[a-z]+", ingredients[0])
    words = [w for w in words if len(w) >= 5]
    return words[0] if words else ""


def is_unbranded(trade_name: str, ingredients) -> bool:
    stem = first_stem(ingredients)
    return bool(stem) and stem in trade_name.lower()


def add_features(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["is_unbranded"] = [
        is_unbranded(t, ing) for t, ing in zip(d["trade_name"], d["ingredients"])
    ]
    # competition = other registered products with the same molecule string
    d["molecule"] = d["scientific_name"]
    size = d.groupby("molecule")["register_no"].transform("count")
    d["n_competitors"] = size - 1
    size_form = d.groupby(["molecule", "dosage_group"])["register_no"].transform("count")
    d["n_competitors_same_form"] = size_form - 1
    d["n_manufacturers_unknown"] = True  # manufacturer is not in the list data
    return d


if __name__ == "__main__":
    d = add_features(pd.read_parquet(IN_PATH))
    d.to_parquet(OUT_PATH, index=False)
    sample = d.sample(30, random_state=42)[
        ["register_no", "scientific_name", "trade_name", "dosage_form", "price", "is_unbranded"]
    ].assign(your_label_generic_or_originator="")
    if CHECK_PATH.exists():  # never overwrite hand-entered labels
        print(f"kept existing {CHECK_PATH.name} (delete it to regenerate)")
    else:
        sample.to_csv(CHECK_PATH, index=False, encoding="utf-8-sig")
    print(f"rows={len(d)}  unbranded={d.is_unbranded.mean():.1%}")
    print(d.n_competitors.describe().round(1).to_string())
    print(f"molecules with >=2 products: {(d.groupby('molecule').size() >= 2).sum()}")
    print(f"wrote {OUT_PATH} and {CHECK_PATH}")
