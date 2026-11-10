# SFDA Drug Price Structure Analysis

An end-to-end analysis of list prices for drugs registered with the Saudi Food and Drug Authority (SFDA): data collection, cleaning, statistical testing and predictive modelling.

## Question

Which registered drugs are priced out of line with comparable products, and what drives price differences between unbranded and brand-named products?

Pricing and reimbursement teams prepare submissions by comparing a product with its comparators. This project shows where a product sits relative to products with the same molecule, dosage form and strength.

## Approach

1. **Collect.** A throttled, cached scraper (`src/scraper.py`) reads the public SFDA drugs list at one request every 2.5 seconds, saves every page and resumes after interruption.
2. **Parse and clean.** Parsing and cleaning turn the pages into a tidy table of 8,171 products (`src/parse.py`, `src/clean.py`).
   - Repeated rows are removed.
   - Strengths are parsed into numeric values, and combination products are flagged.
   - Dosage forms are grouped.
   - Gene and cell therapies are flagged and analysed separately.
   - A data-quality table records every dropped row and each field's parse rate.
3. **Features.** Features add an unbranded flag (trade name contains the molecule name) and competition counts per molecule (`src/features.py`).
4. **Statistics** (`src/analysis.py`)
   - Like-for-like comparison of unbranded and brand-named prices within molecule, dosage form and strength, with bootstrap confidence intervals
   - Spearman correlation and Kruskal-Wallis tests of whether competition changes the price gap, with Holm-corrected pairwise tests
   - Robust z-scores (median and MAD) of log price to flag products far from their comparators
5. **Model** (`src/model.py`). Price is modelled with OLS (robust standard errors) and LightGBM, validated with GroupKFold by molecule so that every test molecule is unseen during training. SHAP explains the gradient-boosting model.
6. **SQL layer.** `sql/` reproduces the cleaning and the analyst-style aggregates in DuckDB (`src/run_sql.py`), and a test reconciles it with the pandas output.
7. **Test.** 47 pytest tests cover parsing, cleaning, features, modelling helpers and the SQL reconciliation.

## Results

| Finding | Value |
|---|---|
| Products analysed | 8,171 cleaned (8,160 in the models) |
| Unbranded vs brand-named price, same molecule, form and strength | median ratio **0.95** (95% bootstrap CI 0.95 to 1.00), 247 comparison cells |
| Effect of competition on that ratio | none detected (Spearman rho 0.00, p = 0.996; Kruskal-Wallis p = 0.24) |
| Price model on unseen molecules (log scale) | LightGBM RMSE **1.89** (R² 0.23); OLS RMSE 1.90 (R² 0.22); dosage-group baseline RMSE 2.05 (R² 0.09) |
| Most important model features (SHAP) | competitor count, strength, injection form, combination flag |
| Products priced far from their comparators (robust z beyond 3.5) | 216 of 3,183 scored |
| SQL (DuckDB) reproduction | The cleaning, data-quality counts and the 247 like-for-like cells (median ratio 0.95) are reproduced in SQL (`sql/`, `python src/run_sql.py`) and reconciled with the Python pipeline row by row in `tests/test_sql.py` |

Unbranded products are priced about 5% below brand-named products of the same molecule, form and strength, and the number of competing registrations does not change that gap. The molecule itself explains most of the price.

Figures and result tables are in `reports/`; the full write-up is in [`reports/REPORT.md`](reports/REPORT.md).

## Interpreting the results

- Prices are list prices from the SFDA drugs list, not transaction prices.
- "Unbranded" means the trade name contains the molecule name. "Brand-named" covers originator brands and branded generics, so the comparison is unbranded vs brand-named, not originator vs generic.
- Flagged products are starting points for review by a pricing team, not evidence of overpricing.

## Project structure

```
src/        scraper.py, parse.py, clean.py, features.py, analysis.py, model.py, run_sql.py
sql/        01_clean.sql, 02_data_quality.sql, 03_aggregates.sql
tests/      test_parse.py, test_clean.py, test_features.py, test_model.py, test_sql.py
reports/    REPORT.md, figures, result tables, sql/ (exported SQL views)
data/       raw/ and clean/ (empty in the repository)
```

## Run it

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

python src/scraper.py            # about 25 minutes; use --start 0 --end 3 to test
python src/parse.py
python src/clean.py
python src/features.py
python src/analysis.py
python src/model.py
python src/run_sql.py            # DuckDB version of the cleaning and aggregates
pytest
```

## Data

The scraped data is not included in this repository. Running the scraper reproduces it from the public SFDA drugs list (https://www.sfda.gov.sa/en/drugs-list). The scraper respects the site's robots.txt and throttles requests. Check SFDA's terms of use before reusing or redistributing the data.

## Tech

Python, pandas, DuckDB (SQL), NumPy, SciPy, statsmodels, scikit-learn, LightGBM, SHAP, BeautifulSoup, matplotlib, pytest.
