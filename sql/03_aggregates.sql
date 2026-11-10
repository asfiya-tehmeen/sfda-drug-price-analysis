-- 03_aggregates.sql  (DuckDB)
-- Analyst-style views a pricing team would query. Gene and cell therapies are
-- excluded from the views, as in the Python analysis.
--   v_dosage_group_summary   products and median price by dosage group
--   v_competition_by_molecule  competing registrations per molecule
--   v_ratio_cells            unbranded vs brand-named price ratio per
--                            (molecule, dosage form, strength) cell
--   v_ratio_summary          the headline ratio across cells

-- Features from src/features.py. The two window counts are the natural tool here:
-- "other registrations with the same molecule" is a count over a partition, and it
-- must be computed on every cleaned row (as pandas does), before any filtering.
CREATE OR REPLACE TABLE products_features AS
WITH stems AS (
    -- first word of at least 5 letters in the first ingredient
    SELECT
        *,
        list_filter(regexp_extract_all(coalesce(first_ingredient, ''), '[a-z]+'), lambda w: length(w) >= 5)[1] AS stem
    FROM products_clean
)
SELECT
    * EXCLUDE (stem),
    -- "unbranded" = the trade name contains the molecule's name. It does NOT mean
    -- generic: brand-named includes originators and branded generics.
    coalesce(stem IS NOT NULL AND contains(lower(trade_name), stem), false)  AS is_unbranded,
    count(*) OVER (PARTITION BY molecule) - 1                                AS n_competitors,
    count(*) OVER (PARTITION BY molecule, dosage_group) - 1                  AS n_competitors_same_form
FROM stems;

-- 1. Products and median price by dosage group, with each group's share of the list.
CREATE OR REPLACE VIEW v_dosage_group_summary AS
SELECT
    dosage_group,
    count(*)                                              AS n_products,
    round(100.0 * count(*) / sum(count(*)) OVER (), 1)    AS pct_of_products,
    median(price)                                         AS median_price,
    quantile_cont(price, 0.25)                            AS p25_price,
    quantile_cont(price, 0.75)                            AS p75_price,
    count(*) FILTER (WHERE is_unbranded)                  AS n_unbranded
FROM products_features
WHERE NOT is_advanced_therapy
GROUP BY dosage_group
ORDER BY n_products DESC;

-- 2. Competing registrations per molecule (registrations, not market share).
CREATE OR REPLACE VIEW v_competition_by_molecule AS
SELECT
    molecule,
    count(*)                                  AS n_registrations,
    count(DISTINCT dosage_group)              AS n_dosage_groups,
    median(price)                             AS median_price,
    rank() OVER (ORDER BY count(*) DESC)      AS competition_rank
FROM products_features
WHERE NOT is_advanced_therapy
GROUP BY molecule
ORDER BY competition_rank, molecule;

-- 3. Like-for-like price ratio: single-ingredient products with a cleanly parsed
-- strength, grouped by (molecule, dosage group, strength). The ratio is the median
-- unbranded price over the median brand-named price, kept only for cells with at
-- least one product on each side. The strength has no unit in the list data.
CREATE OR REPLACE VIEW v_ratio_cells AS
WITH eligible AS (
    SELECT *
    FROM products_features
    WHERE NOT is_advanced_therapy AND NOT is_combo AND strength_parse_ok
),
cells AS (
    SELECT
        molecule,
        dosage_group,
        strength_first,
        count(*) FILTER (WHERE is_unbranded)            AS n_unbranded,
        count(*) FILTER (WHERE NOT is_unbranded)        AS n_brand,
        median(price) FILTER (WHERE is_unbranded)       AS median_price_unbranded,
        median(price) FILTER (WHERE NOT is_unbranded)   AS median_price_brand,
        avg(n_competitors_same_form)                    AS n_competitors_same_form
    FROM eligible
    GROUP BY molecule, dosage_group, strength_first
),
ratios AS (
    SELECT *, median_price_unbranded / median_price_brand AS ratio
    FROM cells
    WHERE n_unbranded >= 1 AND n_brand >= 1
)
SELECT
    *,
    rank() OVER (ORDER BY ratio)  AS ratio_rank_cheapest_first,
    round(percent_rank() OVER (ORDER BY ratio), 3) AS ratio_percentile
FROM ratios
ORDER BY ratio;

-- 4. Headline ratio. The median is taken on the log scale (as in analysis.py), so
-- 0.5x and 2x count as equally far from parity.
CREATE OR REPLACE VIEW v_ratio_summary AS
SELECT
    count(*)                                              AS n_cells,
    exp(median(ln(ratio)))                                AS median_ratio_unbranded_to_brand,
    avg((ratio < 1)::INT)                                 AS share_cells_unbranded_cheaper,
    count(*) FILTER (WHERE n_unbranded >= 2 AND n_brand >= 2) AS n_cells_with_2plus_each_side
FROM v_ratio_cells;
