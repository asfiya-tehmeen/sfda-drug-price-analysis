# Power BI dashboard spec: SFDA price structure

A four-page Power BI Desktop report built **only on the aggregate extracts in `powerbi/data/`**. Budget: about half a day. Build it in Power BI Desktop (free, Windows); nothing here needs a Power BI Pro licence.

**Audience:** a market access or pricing analyst who wants to see how a product sits against its comparators. **One-line story:** unbranded products are about 5% cheaper than brand-named ones like for like, competition does not change that, and raw price medians by form are misleading because they compare different molecules.

## 0. Rules for this dashboard

1. **Aggregates only.** Load only the seven CSVs in `powerbi/data/`. They contain no row-level prices: medians and quartiles are blank where a group has fewer than 3 products, and the cell-level table has ratios but no prices. Do not add any other SFDA data to the file.
2. **Never use "Publish to web".** That makes the report public. Share screenshots (and, if you choose, the `.pbix`, which contains only these aggregates).
3. **Never title or caption anything "overpriced".** No product-level price lists and no outlier ranking on any page. The dashboard describes structure, not individual products.
4. **Medians do not add up.** Never SUM or AVERAGE a median column. Use the measures in section 3.

## 1. Data load

`Home > Get data > Text/CSV`, one query per file. Create a text parameter `DataFolder` (`Transform data > Manage parameters`) holding the full path to `powerbi/data`, and build each source path as `DataFolder & "\form_summary.csv"` so the report keeps working when the folder moves. After re-running `python src/run_sql.py`, click **Refresh**.

| Table (file) | Grain | Rows | Key columns |
|---|---|---|---|
| `headline` | one row | 1 | `n_products_cleaned`, `n_products_in_analysis`, `n_advanced_therapies_excluded`, `n_cells`, `median_ratio_unbranded_to_brand`, `share_cells_unbranded_cheaper`, `n_cells_with_2plus_each_side` |
| `form_summary` | dosage group | 8 | `n_products`, `pct_of_products`, `median_price`, `p25_price`, `p75_price`, `n_unbranded` |
| `form_brandtype` | dosage group × brand type | 16 | `n_products`, `median_price`, `p25_price`, `p75_price` |
| `competition_distribution` | registrations band | 6 | `registrations_band`, `band_order`, `n_molecules` |
| `competition_by_molecule` | molecule | 1,689 | `n_registrations`, `n_dosage_groups`, `competition_rank`, `median_price` |
| `ratio_cells` | molecule × form × strength cell | 247 | `n_unbranded`, `n_brand`, `n_competitors_same_form`, `ratio`, `ratio_rank_cheapest_first` |
| `data_quality` | metric | 9 | `metric`, `value` |

Data types: `strength_first`, `ratio`, prices and `share_cells_unbranded_cheaper` are Decimal; counts are Whole number; text columns stay Text. On `competition_distribution`, set **Sort by column** of `registrations_band` to `band_order`.

## 2. Model

Create one helper table: `dim_dosage_group = DISTINCT(form_summary[dosage_group])` (Modeling > New table).

| Relationship | Cardinality | Cross-filter |
|---|---|---|
| `dim_dosage_group[dosage_group]` → `form_summary[dosage_group]` | one to one | single |
| `dim_dosage_group[dosage_group]` → `form_brandtype[dosage_group]` | one to many | single |
| `dim_dosage_group[dosage_group]` → `ratio_cells[dosage_group]` | one to many | single |
| `competition_by_molecule[molecule]` → `ratio_cells[molecule]` | one to many | single |

`headline`, `competition_distribution` and `data_quality` have no relationships. Put all measures in an empty table named `_Measures` (Enter data, delete the dummy column).

## 3. Measures (DAX)

```dax
-- Headline cards: read from the one-row table, so they do not move with slicers
Products cleaned        = MAX ( headline[n_products_cleaned] )
Products in analysis    = MAX ( headline[n_products_in_analysis] )
Advanced therapies excl = MAX ( headline[n_advanced_therapies_excluded] )

-- Cell-level measures: these DO respond to slicers (dosage group, molecule)
Cells                   = COUNTROWS ( ratio_cells )
Median ratio            = EXP ( MEDIANX ( ratio_cells, LN ( ratio_cells[ratio] ) ) )   -- median taken on the log scale
Price gap vs brand      = [Median ratio] - 1                                             -- format as %; unsliced = -4.8%
Cells unbranded cheaper = COUNTROWS ( FILTER ( ratio_cells, ratio_cells[ratio] < 1 ) )
Share unbranded cheaper = DIVIDE ( [Cells unbranded cheaper], [Cells] )
Cells with 2+ each side = CALCULATE ( COUNTROWS ( ratio_cells ),
                              ratio_cells[n_unbranded] >= 2, ratio_cells[n_brand] >= 2 )

-- Medians: valid only where the context is a single stored row (never SUM/AVERAGE them)
Median price (form)     = IF ( HASONEVALUE ( form_summary[dosage_group] ),
                               MAX ( form_summary[median_price] ) )
Median price (form x brand) = IF ( COUNTROWS ( form_brandtype ) = 1,
                               MAX ( form_brandtype[median_price] ) )

-- Additive counts are safe to SUM
Products (form x brand) = SUM ( form_brandtype[n_products] )
Molecules               = SUM ( competition_distribution[n_molecules] )
```

Calculated column on `ratio_cells` (display bands, not an analysis result), plus a hidden sort column:

```dax
Ratio band = SWITCH ( TRUE (),
    ratio_cells[ratio] < 0.5,  "< 0.5",
    ratio_cells[ratio] < 0.9,  "0.5 to 0.9",
    ratio_cells[ratio] <= 1.1, "0.9 to 1.1",
    ratio_cells[ratio] < 2,    "1.1 to 2",
    "2 or more" )

Ratio band order = SWITCH ( TRUE (),
    ratio_cells[ratio] < 0.5, 1, ratio_cells[ratio] < 0.9, 2,
    ratio_cells[ratio] <= 1.1, 3, ratio_cells[ratio] < 2, 4, 5 )
```
Set **Sort by column** of `Ratio band` to `Ratio band order`.

## 4. Pages

Canvas 16:9, Segoe UI. Colours: **Unbranded `#2F6DB5` (blue)**, **Brand-named `#E08A1E` (orange)**, neutrals grey. These are colour-blind safe; use them consistently on every page. Every chart title states what is shown, not just the field names. Put the footer text from section 5 on every page.

### Page 1: Overview
- Cards (unsliced): **Products cleaned** (8,171), **Cells** (247), **Median ratio** (0.95, two decimals), **Share unbranded cheaper** (56.7%).
- Bar chart: **products by dosage group**, `form_summary[dosage_group]` by `n_products` (sorted descending), data labels on.
- Text box (the answer): "Unbranded products are about 5% cheaper than brand-named products of the same molecule, form and strength (median ratio 0.95, 95% bootstrap CI 0.95 to 1.00). Competition does not change that gap." The CI comes from `analysis.py`, so it is typed text, not a measure.

### Page 2: Price structure
- Slicer: `dim_dosage_group[dosage_group]`.
- Clustered bar: axis `dim_dosage_group[dosage_group]`, legend `form_brandtype[brand_type]`, value `Median price (form x brand)`. **Value axis scale: Log.** Title: "Unadjusted median price: different molecules, not like for like".
- Table: `dosage_group`, `Median price (form)`, `p25_price`, `p75_price` (as MAX), `n_products`.
- Text box (important): "These medians compare different molecules. Unbranded capsules (median 8,807.55) look dearer than brand-named capsules (93.75) and unbranded injections look cheaper (47.50 vs 631.15), because unbranded names cluster on different molecules. The like-for-like comparison is on page 4." This page is deliberate: it shows why raw medians mislead.

### Page 3: Competition
- Column chart: `competition_distribution[registrations_band]` (sorted by `band_order`) by `n_molecules`. Title: "How many molecules have 1, 2, 3-5, ... registrations".
- Bar chart: top 15 molecules by `n_registrations` (visual-level Top N filter on `n_registrations`; the 15th has 44). Title: "Most-registered molecules (registrations, not market share)".
- Scatter: X `ratio_cells[n_competitors_same_form]`, Y `ratio_cells[ratio]` (log scale), details `molecule`. Add a constant line at **1** (Analytics pane). Title: "Competition vs unbranded/brand-named price ratio, per cell".
- Text box: "Spearman rho 0.00 (p = 0.996) and Kruskal-Wallis p = 0.24 across low/mid/high competition bands: no detectable relationship. Tests run in `src/analysis.py`; competition = registered products with the same molecule and form."

### Page 4: Like-for-like explorer
- Slicers: `dim_dosage_group[dosage_group]`; `competition_by_molecule[molecule]` (dropdown with search).
- Cards: **Cells**, **Median ratio**, **Share unbranded cheaper** (these respond to the slicers).
- Column chart: axis `Ratio band`, value `Cells` (expected counts in section 6).
- Table: `molecule`, `dosage_group`, `strength_first`, `n_unbranded`, `n_brand`, `ratio`. Conditional formatting on `ratio`: below 0.9 blue, 0.9 to 1.1 grey, above 1.1 orange. Sort by `ratio`.
- Text box: "Ratio = median unbranded price / median brand-named price within a cell (same molecule, dosage group, strength). 21 cells have a ratio of exactly 1. Only 70 cells have 2+ products on each side, so many cells compare single products. Strength has no unit in the source."

### Optional page 5: Data and limits
- Table of `data_quality` (metric, value).
- Text list: list prices not transaction prices; one snapshot (2026-11-09); no pack size or strength unit; about 10% of source pages returned no data; unbranded is not generic (hand-check: 4 of 4 flagged rows were generics, but the flag caught only 4 of 22 generics); gene and cell therapies excluded (11).

## 5. Footer text (every page)

> SFDA drugs list, scraped 2026-11-09. List prices, not transaction prices. "Unbranded" = trade name contains the molecule name; "brand-named" includes originators and branded generics. 11 gene and cell therapies excluded.

## 6. Verify before you screenshot

With **no slicers applied**, the dashboard must reproduce the report:

| Check | Expected | Source |
|---|---|---|
| Products cleaned | 8,171 | `reports/data_quality.csv` |
| Products in analysis / advanced excluded | 8,160 / 11 | `reports/model_results.json`, `data_quality.csv` |
| Cells | 247 | `reports/stats_results.json` |
| Median ratio | 0.9518 (shows 0.95) | `reports/stats_results.json` |
| Price gap vs brand | -4.8% | 1 - 0.9518 |
| Share unbranded cheaper | 56.7% (140 of 247 cells) | `reports/stats_results.json` |
| Cells with 2+ each side | 70 | `reports/sql/ratio_summary.csv` |
| Ratio bands (< 0.5 / 0.5-0.9 / 0.9-1.1 / 1.1-2 / 2+) | 28 / 56 / 99 / 34 / 30 | `powerbi/data/ratio_cells.csv` |
| Cells by dosage group | tablet 99, injection_infusion 98, capsule 27, oral_liquid 7, topical 6, ophthalmic 5, other 3, inhaled_nasal 2 | `powerbi/data/ratio_cells.csv` |
| Molecules by registrations band (1 / 2 / 3-5 / 6-10 / 11-25 / 26+) | 654 / 318 / 338 / 194 / 135 / 50 (sum 1,689) | `competition_distribution.csv` |
| Most-registered molecule | tadalafil, 88 | `competition_by_molecule.csv` |
| Form summary, tablet | 3,656 products, median 73.50 | `form_summary.csv` |

If any number differs, fix the measure or the relationship, do not edit the data.

## 7. Finish

1. Save as `powerbi/SFDA_Price_Structure.pbix`.
2. Export each page as an image (File > Export > or screenshot at 100% zoom) to `powerbi/screenshots/`, named `01_overview.png` and so on.
3. In `README.md`, add a short "Dashboard" section with the Overview and Like-for-like screenshots, and one sentence saying it is built on the aggregate extracts in `powerbi/data/`. Do not claim anything the screenshots do not show.
4. Decide whether to commit the `.pbix`. It embeds only the aggregates above, so it is consistent with the repository's no-republishing rule, but it is a large binary; screenshots plus the extracts are enough for most readers.

## 8. What this adds to your profile

You can truthfully say you built an aggregate-only Power BI report with a star-style model (one dimension, DAX measures including log-scale median logic), reconciled its figures to a Python and SQL pipeline, and designed it to avoid misleading comparisons. Only add "Power BI" to your CV once you have built it.
