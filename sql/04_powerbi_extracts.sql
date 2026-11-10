-- 04_powerbi_extracts.sql  (DuckDB)
-- Aggregate-only tables for the Power BI dashboard (see powerbi/DASHBOARD_SPEC.md).
-- Privacy rule for the dashboard: no row-level prices. A median or quartile is blanked
-- (NULL) when it is based on fewer than 3 products, so it cannot expose a single
-- product's price. Gene and cell therapies are excluded, as in the Python analysis.

-- Products and price by dosage group (all products in the group).
CREATE OR REPLACE VIEW v_pbi_form_summary AS
SELECT dosage_group, n_products, pct_of_products, median_price, p25_price, p75_price, n_unbranded
FROM v_dosage_group_summary;

-- Same, split by unbranded vs brand-named. Medians cannot be combined across rows,
-- so each row is one (dosage group, brand type) pair.
CREATE OR REPLACE VIEW v_pbi_form_brandtype AS
SELECT
    dosage_group,
    CASE WHEN is_unbranded THEN 'Unbranded' ELSE 'Brand-named' END      AS brand_type,
    count(*)                                                            AS n_products,
    CASE WHEN count(*) >= 3 THEN median(price) END                      AS median_price,
    CASE WHEN count(*) >= 3 THEN quantile_cont(price, 0.25) END         AS p25_price,
    CASE WHEN count(*) >= 3 THEN quantile_cont(price, 0.75) END         AS p75_price
FROM products_features
WHERE NOT is_advanced_therapy
GROUP BY dosage_group, is_unbranded
ORDER BY dosage_group, brand_type;

-- How many molecules have 1, 2, 3-5, ... registrations (display bands; counts only).
CREATE OR REPLACE VIEW v_pbi_competition_distribution AS
WITH per_molecule AS (
    SELECT molecule, count(*) AS n
    FROM products_features
    WHERE NOT is_advanced_therapy
    GROUP BY molecule
),
banded AS (
    SELECT
        CASE WHEN n = 1 THEN 1 WHEN n = 2 THEN 2 WHEN n <= 5 THEN 3
             WHEN n <= 10 THEN 4 WHEN n <= 25 THEN 5 ELSE 6 END         AS band_order
    FROM per_molecule
)
SELECT
    CASE band_order WHEN 1 THEN '1' WHEN 2 THEN '2' WHEN 3 THEN '3-5'
                    WHEN 4 THEN '6-10' WHEN 5 THEN '11-25' ELSE '26+' END AS registrations_band,
    band_order,
    count(*)                                                            AS n_molecules
FROM banded
GROUP BY band_order
ORDER BY band_order;

-- Registrations per molecule. Median price only where the molecule has 3+ registrations.
CREATE OR REPLACE VIEW v_pbi_competition_by_molecule AS
SELECT
    molecule,
    n_registrations,
    n_dosage_groups,
    competition_rank,
    CASE WHEN n_registrations >= 3 THEN median_price END                AS median_price
FROM v_competition_by_molecule;

-- Like-for-like cells WITHOUT the median prices (many cells hold a single product per
-- side, so a cell median would be an individual price). The ratio is kept.
CREATE OR REPLACE VIEW v_pbi_ratio_cells AS
SELECT
    molecule,
    dosage_group,
    strength_first,
    n_unbranded,
    n_brand,
    n_competitors_same_form,
    ratio,
    ratio_rank_cheapest_first
FROM v_ratio_cells;

-- One row of headline numbers for the KPI cards.
CREATE OR REPLACE VIEW v_pbi_headline AS
SELECT
    (SELECT value FROM data_quality WHERE metric = 'rows_out')::INTEGER                   AS n_products_cleaned,
    (SELECT count(*) FROM products_features WHERE NOT is_advanced_therapy)                AS n_products_in_analysis,
    (SELECT count(*) FROM products_features WHERE is_advanced_therapy)                    AS n_advanced_therapies_excluded,
    n_cells,
    median_ratio_unbranded_to_brand,
    share_cells_unbranded_cheaper,
    n_cells_with_2plus_each_side
FROM v_ratio_summary;
