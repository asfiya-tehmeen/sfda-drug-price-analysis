-- 02_data_quality.sql  (DuckDB)
-- Rebuilds reports/data_quality.csv from the tables created by 01_clean.sql:
-- rows in, rows dropped per reason, rows out, and parse rates. Metric names and
-- order match the pandas file so the two can be compared line by line.

CREATE OR REPLACE TABLE data_quality AS
WITH counts AS (
    SELECT
        (SELECT count(*) FROM raw_list)       AS n_in,
        (SELECT count(*) FROM stg_dedup)      AS n_deduped,
        (SELECT count(*) FROM products_clean) AS n_out
),
parse_rates AS (
    SELECT
        round(100 * avg(strength_parse_ok::INT), 1)             AS strength_ok_pct,
        round(100 * avg(strength_matches_ingredients::INT), 1)  AS strength_match_pct,
        count(*) FILTER (WHERE is_combo)                        AS n_combo,
        count(*) FILTER (WHERE is_advanced_therapy)             AS n_advanced,
        count(*) FILTER (WHERE dosage_group = 'other')          AS n_other_form
    FROM products_clean
)
SELECT metric, value
FROM (
    SELECT 1 AS ord, 'rows_in'                               AS metric, n_in::DOUBLE                AS value FROM counts
    UNION ALL SELECT 2, 'dropped_duplicate_register_no',          (n_in - n_deduped)::DOUBLE        FROM counts
    UNION ALL SELECT 3, 'dropped_price_missing_or_nonpositive',   (n_deduped - n_out)::DOUBLE       FROM counts
    UNION ALL SELECT 4, 'rows_out',                               n_out::DOUBLE                     FROM counts
    UNION ALL SELECT 5, 'parse_ok_strength_pct',                  strength_ok_pct                   FROM parse_rates
    UNION ALL SELECT 6, 'strength_matches_ingredients_pct',       strength_match_pct                FROM parse_rates
    UNION ALL SELECT 7, 'combination_products',                   n_combo::DOUBLE                   FROM parse_rates
    UNION ALL SELECT 8, 'advanced_therapies_flagged',             n_advanced::DOUBLE                FROM parse_rates
    UNION ALL SELECT 9, 'dosage_group_other',                     n_other_form::DOUBLE              FROM parse_rates
)
ORDER BY ord;
