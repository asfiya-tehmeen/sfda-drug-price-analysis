"""Phase 3-4: exploration figures + statistics. Advanced therapies are excluded
(modelled separately). Everything written to reports/.

Cells = (molecule, dosage_group, strength_first) for single-ingredient products
with a cleanly parsed strength, so we compare like with like. Strength has no
unit in the list data, so a cell can still mix units in rare cases.

Run from project root:  python src/analysis.py
"""
import json
from itertools import combinations
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402
from statsmodels.stats.multitest import multipletests  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
RNG = np.random.default_rng(42)
N_BOOT = 2000
MAD_FLOOR = 0.10
CELL = ["molecule", "dosage_group", "strength_first"]


def boot_ci(values, n=N_BOOT, stat=np.median):
    values = np.asarray(values)
    draws = [stat(RNG.choice(values, len(values))) for _ in range(n)]
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def figures(d):
    fig, ax = plt.subplots(figsize=(8, 4))
    order = d.groupby("dosage_group").log_price.median().sort_values().index
    ax.boxplot([d.loc[d.dosage_group == g, "log_price"] for g in order], orientation="horizontal", showfliers=False)
    ax.set_yticklabels(order)
    ax.set_xlabel("log(price) [SAR assumed]")
    ax.set_title("Price by dosage group (advanced therapies excluded)")
    fig.tight_layout()
    fig.savefig(REPORTS / "fig_price_by_form.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 4))
    for flag, name in [(True, "unbranded"), (False, "brand-named")]:
        ax.hist(d.loc[d.is_unbranded == flag, "log_price"], bins=40, alpha=0.55, label=name, density=True)
    ax.set_xlabel("log(price)")
    ax.legend()
    ax.set_title("Price distribution: unbranded vs brand-named")
    fig.tight_layout()
    fig.savefig(REPORTS / "fig_price_by_brandtype.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(np.log1p(d.n_competitors), bins=40)
    ax.set_xlabel("log(1 + competing products with same molecule)")
    ax.set_title("Competition per product")
    fig.tight_layout()
    fig.savefig(REPORTS / "fig_competition.png", dpi=150)
    plt.close(fig)


def ratio_cells(d):
    s = d[(~d.is_combo) & d.strength_parse_ok].copy()
    rows = []
    for key, g in s.groupby(CELL):
        u = g.loc[g.is_unbranded, "price"].to_numpy()
        b = g.loc[~g.is_unbranded, "price"].to_numpy()
        if len(u) < 1 or len(b) < 1:
            continue
        ratio = np.median(u) / np.median(b)
        row = dict(zip(CELL, key), n_unbranded=len(u), n_brand=len(b), ratio=ratio,
                   n_competitors_same_form=g.n_competitors_same_form.mean())
        if len(u) >= 2 and len(b) >= 2:  # bootstrap CI only with >=2 each side
            lo = [np.median(RNG.choice(u, len(u))) / np.median(RNG.choice(b, len(b))) for _ in range(1000)]
            row["ci_lo"], row["ci_hi"] = np.percentile(lo, [2.5, 97.5])
        rows.append(row)
    return pd.DataFrame(rows)


def outliers(d):
    s = d[(~d.is_combo) & d.strength_parse_ok].copy()
    g = s.groupby(CELL)["log_price"]
    s["cell_n"] = g.transform("count")
    s["cell_med"] = g.transform("median")
    s["cell_mad"] = g.transform(lambda x: np.median(np.abs(x - np.median(x))))
    s = s[s.cell_n >= 5]
    # Floor the MAD at 0.10 log units (~10% price spread): cells where products share
    # near-identical prices have MAD ~ 0 and would give absurd z-scores.
    s["robust_z"] = 0.6745 * (s.log_price - s.cell_med) / s.cell_mad.clip(lower=MAD_FLOOR)
    s["price_vs_cell_median"] = np.exp(s.log_price - s.cell_med)
    cols = ["molecule", "trade_name", "dosage_form", "strength_raw", "price", "cell_n",
            "price_vs_cell_median", "robust_z", "is_unbranded"]
    top = s.reindex(s.robust_z.abs().sort_values(ascending=False).index).head(20)[cols]
    return top, len(s)


def main():
    d_all = pd.read_parquet(ROOT / "data" / "clean" / "features.parquet")
    d = d_all[~d_all.is_advanced_therapy].copy()
    res = {"n_all": len(d_all), "n_main": len(d), "n_advanced_excluded": int(d_all.is_advanced_therapy.sum())}

    figures(d)

    # ---- price level by brand type (descriptive, not like-for-like) ----
    res["median_price_unbranded"] = float(d.loc[d.is_unbranded, "price"].median())
    res["median_price_brand_named"] = float(d.loc[~d.is_unbranded, "price"].median())
    res["n_unbranded"] = int(d.is_unbranded.sum())

    # ---- like-for-like ratio ----
    cells = ratio_cells(d)
    res["n_cells"] = len(cells)
    if len(cells) >= 10:
        lr = np.log(cells.ratio.to_numpy())
        res["median_ratio_unbranded_to_brand"] = float(np.exp(np.median(lr)))
        lo, hi = boot_ci(lr)
        res["ratio_ci95"] = [float(np.exp(lo)), float(np.exp(hi))]
        res["share_cells_unbranded_cheaper"] = float((cells.ratio < 1).mean())

        # ---- competition vs ratio ----
        rho, p = stats.spearmanr(cells.n_competitors_same_form, cells.ratio)
        res["spearman_rho_competition_vs_ratio"] = float(rho)
        res["spearman_p"] = float(p)

        cells["band"] = pd.qcut(cells.n_competitors_same_form, 3, labels=["low", "mid", "high"], duplicates="drop")
        groups = {b: g.ratio.to_numpy() for b, g in cells.groupby("band", observed=True) if len(g) > 1}
        res["band_sizes"] = {str(k): len(v) for k, v in groups.items()}
        if len(groups) >= 2:
            h, p = stats.kruskal(*groups.values())
            res["kruskal_H"], res["kruskal_p"] = float(h), float(p)
            pairs = list(combinations(groups, 2))
            raw = [stats.mannwhitneyu(groups[a], groups[b]).pvalue for a, b in pairs]
            adj = multipletests(raw, method="holm")[1]
            res["pairwise_mwu_holm"] = {f"{a}-{b}": float(x) for (a, b), x in zip(pairs, adj)}
    cells.to_csv(REPORTS / "ratio_cells.csv", index=False)

    # ---- outliers ----
    top, n_scored = outliers(d)
    res["n_scored_for_outliers"] = int(n_scored)
    top.to_csv(REPORTS / "outliers_top20.csv", index=False)

    res["hhi"] = "skipped: no ATC or therapeutic class in the list data"
    (REPORTS / "stats_results.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))
    print(top[["molecule", "trade_name", "price", "price_vs_cell_median", "robust_z"]].head(10).to_string())


if __name__ == "__main__":
    main()
