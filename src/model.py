"""Phase 5: baselines, hedonic OLS, LightGBM + SHAP. Validated with GroupKFold by molecule.

Advanced therapies are excluded (11 rows, reported descriptively instead).
Features are limited to what the SFDA list provides: no manufacturer, ATC class,
strength unit or pack size.

Run from project root:  python src/model.py
"""
import json
from pathlib import Path

import lightgbm as lgb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import shap  # noqa: E402
import statsmodels.api as sm  # noqa: E402
from sklearn.metrics import r2_score  # noqa: E402
from sklearn.model_selection import GroupKFold, KFold  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
SEED = 42
N_SPLITS = 5


def metrics(y_log, pred_log):
    rmse = float(np.sqrt(np.mean((y_log - pred_log) ** 2)))
    ape = np.abs(np.exp(pred_log) - np.exp(y_log)) / np.exp(y_log)
    return {"rmse_log": rmse, "r2_log": float(r2_score(y_log, pred_log)),
            "mape": float(ape.mean()), "median_ape": float(np.median(ape))}


def build(d):
    X = pd.DataFrame(index=d.index)
    X["log_strength"] = np.log1p(d.strength_first)  # NaN where unparsed
    X["strength_missing"] = d.strength_first.isna().astype(int)
    X["is_combo"] = d.is_combo.astype(int)
    X["n_ingredients"] = d.n_ingredients
    X["is_unbranded"] = d.is_unbranded.astype(int)
    X["log_competitors"] = np.log1p(d.n_competitors)
    X["log_competitors_form"] = np.log1p(d.n_competitors_same_form)
    forms = pd.get_dummies(d.dosage_group, prefix="form", drop_first=True, dtype=int)
    return pd.concat([X, forms], axis=1)


def ols_fit_predict(Xtr, ytr, Xte):
    med = Xtr["log_strength"].median()
    f = lambda X: sm.add_constant(X.assign(log_strength=X.log_strength.fillna(med)), has_constant="add")  # noqa: E731
    fit = sm.OLS(ytr, f(Xtr)).fit(cov_type="HC3")
    return fit.predict(f(Xte)), fit


def lgb_model():
    return lgb.LGBMRegressor(n_estimators=400, learning_rate=0.05, num_leaves=31,
                             min_child_samples=20, subsample=0.8, subsample_freq=1,
                             colsample_bytree=0.8, random_state=SEED, verbose=-1)


def main():
    d = pd.read_parquet(ROOT / "data" / "clean" / "features.parquet")
    d = d[~d.is_advanced_therapy].reset_index(drop=True)
    y = d.log_price.to_numpy()
    X = build(d)
    groups = d.molecule.to_numpy()
    n_mol = len(set(groups))

    oof = {k: np.zeros(len(d)) for k in ["baseline_form_median", "ols", "lightgbm"]}
    for tr, te in GroupKFold(n_splits=N_SPLITS).split(X, y, groups):
        form_med = pd.Series(y[tr]).groupby(d.dosage_group.iloc[tr].to_numpy()).median()
        oof["baseline_form_median"][te] = d.dosage_group.iloc[te].map(form_med).fillna(np.median(y[tr])).to_numpy()
        oof["ols"][te], _ = ols_fit_predict(X.iloc[tr], y[tr], X.iloc[te])
        m = lgb_model().fit(X.iloc[tr], y[tr])
        oof["lightgbm"][te] = m.predict(X.iloc[te])

    # README baseline (molecule median) under ORDINARY random folds: optimistic reference
    mol_med_pred = np.zeros(len(d))
    for tr, te in KFold(N_SPLITS, shuffle=True, random_state=SEED).split(X):
        mm = pd.Series(y[tr]).groupby(groups[tr]).median()
        fallback = d.dosage_group.iloc[te].map(pd.Series(y[tr]).groupby(d.dosage_group.iloc[tr].to_numpy()).median())
        mol_med_pred[te] = pd.Series(groups[te]).map(mm).fillna(fallback.reset_index(drop=True)).to_numpy()

    res = {"n_rows": len(d), "n_molecules": n_mol, "cv": f"GroupKFold({N_SPLITS}) by molecule",
           "baseline_form_median_groupcv": metrics(y, oof["baseline_form_median"]),
           "baseline_molecule_median_RANDOM_cv_optimistic": metrics(y, mol_med_pred),
           "ols_groupcv": metrics(y, oof["ols"]),
           "lightgbm_groupcv": metrics(y, oof["lightgbm"])}

    base = res["baseline_form_median_groupcv"]["rmse_log"]
    res["beats_fair_baseline"] = {k: bool(res[f"{k}_groupcv"]["rmse_log"] < base) for k in ["ols", "lightgbm"]}

    # OLS coefficients on the full data (robust SE)
    _, fit = ols_fit_predict(X, y, X)
    coef = pd.DataFrame({"coef": fit.params, "se_HC3": fit.bse, "p": fit.pvalues}).round(4)
    coef.to_csv(REPORTS / "ols_coefficients.csv")
    res["ols_unbranded_effect_pct"] = float((np.exp(fit.params["is_unbranded"]) - 1) * 100)
    res["ols_unbranded_p"] = float(fit.pvalues["is_unbranded"])

    # SHAP on full-data LightGBM
    full = lgb_model().fit(X, y)
    sample = X.sample(min(2000, len(X)), random_state=SEED)
    sv = shap.TreeExplainer(full).shap_values(sample)
    imp = pd.Series(np.abs(sv).mean(axis=0), index=X.columns).sort_values(ascending=False)
    res["shap_mean_abs_top"] = {k: round(float(v), 4) for k, v in imp.head(6).items()}
    fig, ax = plt.subplots(figsize=(6, 4))
    imp.head(10)[::-1].plot.barh(ax=ax)
    ax.set_xlabel("mean |SHAP| (log price)")
    ax.set_title("LightGBM feature importance")
    fig.tight_layout()
    fig.savefig(REPORTS / "fig_shap.png", dpi=150)
    plt.close(fig)

    # top-20 unusual products from out-of-fold residuals of the better model
    best = "lightgbm" if res["lightgbm_groupcv"]["rmse_log"] <= res["ols_groupcv"]["rmse_log"] else "ols"
    res["residual_model"] = best
    d["pred_price"] = np.exp(oof[best])
    d["residual_log"] = y - oof[best]
    d["price_vs_expected"] = np.exp(d.residual_log)
    cols = ["molecule", "trade_name", "dosage_form", "strength_raw", "price", "pred_price",
            "price_vs_expected", "residual_log", "is_unbranded"]
    top = d.reindex(d.residual_log.abs().sort_values(ascending=False).index).head(20)[cols]
    top.to_csv(REPORTS / "top20_model_residuals.csv", index=False)

    (REPORTS / "model_results.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))
    print(top[["molecule", "trade_name", "price", "pred_price", "price_vs_expected"]].head(10).to_string())


if __name__ == "__main__":
    main()
