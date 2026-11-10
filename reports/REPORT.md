# SFDA Drug Price Structure Analysis

**Scrape date:** 2026-11-09 | **Source:** SFDA Drugs List (https://www.sfda.gov.sa/en/drugs-list), list pages only

## Answer

Within the SFDA list, products whose trade name is just the molecule name ("unbranded") are priced about **5% below brand-named products of the same molecule, form and strength** (median ratio 0.95, 95% bootstrap CI 0.95 to 1.00, 247 comparison cells). The effect is small and the spread is wide (cell ratios from 0.03 to 15.7). The **number of competing registrations had no detectable effect** on that ratio (Spearman rho = 0.00, p = 0.996; Kruskal-Wallis p = 0.24). **Which molecule a product contains explains most of its price**; the other fields in the list explain little (see Findings 3). The list cannot separate originators from branded generics, and it has no pack size, so **this analysis cannot say which products are overpriced**. The flagged products are questions for a pricing team to look at, not conclusions.

## Data

- 460 list pages requested; 413 returned data and 47 returned "No Results Found" every time (about 10%, page numbers in `scraping_notes.md`). 8,246 rows parsed, 8,171 after cleaning (74 repeated register numbers, 1 zero price dropped).
- Fields available: scientific name, trade name, strength (no unit), dosage form, price (currency not stated on the page; assumed SAR), register number.
- Not available: manufacturer, ATC class, strength unit, pack size, registration date. The detail pages show them in a browser but load them with JavaScript, and were not scraped.
- Strength parsed cleanly for 98.9% of rows; 1,297 are combination products; 11 gene or cell therapies were flagged and kept out of the models.
- Scraping was throttled (one request every 2.5 s), cached and for private analysis. The terms of use are ambiguous on automated access; see `scraping_notes.md`. The raw data is not published.

## Findings

1. **Unbranded vs brand-named, like for like.** Median ratio 0.95 (CI 0.95 to 1.00); unbranded is cheaper in 57% of 247 cells. Only 70 cells have two or more products on each side, so many cells compare single products. `is_unbranded` means the trade name contains the molecule name (10.3% of products). A brand-named product can be an originator or a branded generic (for example LOVERA for tadalafil), so this is **not** an originator-versus-generic comparison. Hand-check on 30 random rows (22 generic, 8 originator by my own labelling): all 4 products flagged unbranded were generics (4/4), but the flag caught only 4 of the 22 generics (18% recall). The 26 brand-named rows were 18 generics and 8 originators, so roughly two thirds of the "brand-named" group are branded generics. The 0.95 ratio is therefore mostly branded generics against unbranded generics, not originators against generics. The labels are one person's judgement from names and prices alone, with no registration data to check against, and n = 30 makes these shares rough.
2. **Competition and the price ratio.** No relationship (rho = 0.00, p = 0.996). Across low, mid and high competition bands (99, 68, 80 cells) the ratio does not differ (H = 2.86, p = 0.24; all Holm-adjusted pairwise p > 0.2). Competition is counted as registered products with the same molecule, not market share.
3. **What predicts price.** With 5-fold GroupKFold by molecule (every test molecule unseen), LightGBM reached RMSE 1.89 on the log scale (R² 0.23) and OLS 1.90 (R² 0.22), against 2.05 (R² 0.09) for a dosage-group median baseline. Both beat the baseline modestly; no significance test was run. A molecule-median baseline under ordinary random folds reaches R² 0.72, which shows the molecule carries most of the price signal, but it cannot price a new molecule. SHAP ranks competitor count, strength, injection form and the combination flag highest.
4. **Gene and cell therapies are a separate price tier.** The 11 flagged products (Libmeldy, Hemgenix, Casgevy, Zolgensma, Carvykti, Yescarta, Tecartus, Breyanzi, Kymriah, Luxturna) list at roughly 1.5 million to 14.4 million. They are excluded from all statistics and models.
5. **Products flagged for review.** `outliers_top20.csv` (robust z-score of log price within molecule, form and strength) and `top20_model_residuals.csv` (largest out-of-fold residuals) list products priced far from comparators. Both lists are dominated by specialty and rare-disease drugs and by pack-size differences, for example Evrysdi, Prevymis, Imbruvica and Translarna in the model list. They show where the model lacks information, not where prices are wrong.

## Limitations

- List price only; not what hospitals or NUPCO pay. One snapshot, no price history, no sales volume.
- **No pack size**: price is per pack, so price differences can reflect pack size. This likely drives many outliers (for example one atorvastatin range sits about 16 times above its cell median).
- **No strength unit**: a strength cell can mix units. No manufacturer or ATC class, so the README's manufacturer term and HHI by therapeutic class were not done.
- About 10% of pages returned no data, and repeated rows across page boundaries suggest the site's ordering shifts, so some products may be missing even from loaded pages. The direction of any bias is unknown.
- Originators cannot be separated from branded generics.
- The OLS coefficient for unbranded (-47%) compares across molecules and is confounded by molecule type; it is not reported as a finding. Use the like-for-like ratio instead.
- The MAPE is very high (several hundred percent) because of large misses on expensive drugs; do not read it as accuracy.
- Flagged products are hypotheses for review, not proof of overpricing. Nothing here concerns the UAE.

## Reproduce

```
python src/scraper.py   # cached to data/raw/
python src/parse.py
python src/clean.py
python src/features.py
python src/analysis.py
python src/model.py
python src/run_sql.py   # DuckDB (sql/01-03): cleaning and aggregates, exported to reports/sql/
pytest                  # includes tests/test_sql.py, which reconciles SQL with the pandas pipeline
```

The SQL layer reproduces the cleaning (8,246 rows in, 8,171 out, same drop counts), the 247 like-for-like cells and the median ratio of 0.95 from `data/clean/list_raw_parsed.csv`; `tests/test_sql.py` checks row-level agreement with the Python pipeline.
