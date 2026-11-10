-- 01_clean.sql  (DuckDB)
-- Same cleaning rules as src/clean.py, applied to the parsed list table.
-- Input : data/clean/list_raw_parsed.csv  (from src/parse.py; every field is raw text)
-- Output: tables raw_list, stg_dedup, products_clean
-- Run via src/run_sql.py (paths are relative to the project root).

-- Python's str.strip() and \s also match tabs, newlines and Unicode spaces such as the
-- non-breaking space (U+00A0, present in some trade names). DuckDB's trim() removes only
-- spaces and RE2's \s is ASCII-only, so [\s\pZ\x{85}] reproduces Python's whitespace class.
CREATE OR REPLACE MACRO py_strip(x) AS regexp_replace(x, '^[\s\pZ\x{85}]+|[\s\pZ\x{85}]+$', '', 'g');
CREATE OR REPLACE MACRO py_squash(x) AS py_strip(regexp_replace(x, '[\s\pZ\x{85}]+', ' ', 'g'));

-- All columns as text so register numbers keep leading zeros (e.g. 0406269864).
-- rn keeps file order, which decides which duplicate is "first".
CREATE OR REPLACE TABLE raw_list AS
SELECT row_number() OVER () AS rn, *
FROM read_csv('data/clean/list_raw_parsed.csv', header = true, all_varchar = true);

-- Rule 1: the site's paging repeats rows across page boundaries. Keep the first
-- row per register number (pandas: drop_duplicates('register_no', keep='first')).
CREATE OR REPLACE TABLE stg_dedup AS
SELECT *
FROM raw_list
QUALIFY row_number() OVER (PARTITION BY register_no ORDER BY rn) = 1;

-- Rules 2-6 in one pass over the de-duplicated rows.
CREATE OR REPLACE TABLE products_clean AS
WITH priced AS (
    -- Rule 2: drop missing, unparsable or non-positive prices.
    SELECT *, TRY_CAST(price AS DOUBLE) AS price_num
    FROM stg_dedup
    WHERE TRY_CAST(price AS DOUBLE) > 0
),
named AS (
    -- Rule 3: lower-case, squash whitespace, strip trailing '*' from trade names.
    SELECT
        rn,
        register_no,
        price_num AS price,
        py_squash(lower(coalesce(scientific_name, '')))                         AS molecule,
        py_squash(regexp_replace(coalesce(trade_name, ''), '\*+[\s\pZ\x{85}]*$', ''))      AS trade_name,
        py_strip(coalesce(dosage_form, ''))                                     AS dosage_form,
        strength                                                                AS strength_raw,
        py_squash(strength)                                                     AS strength_norm
    FROM priced
),
parsed AS (
    SELECT
        *,
        -- Rule 4: ingredients = non-empty comma-separated pieces; order is kept so
        -- it stays aligned with the strength values.
        list_filter(list_transform(string_split(molecule, ','), lambda x: py_strip(x)), lambda x: x <> '') AS ingredients,
        -- Rule 5: strength counts only if it is a plain list of numbers ("10,5", "0.9").
        coalesce(regexp_full_match(strength_norm, '\d+(\.\d+)?([\s\pZ\x{85}]*,[\s\pZ\x{85}]*\d+(\.\d+)?)*'), false)  AS strength_parse_ok
    FROM named
)
SELECT
    rn,
    register_no,
    molecule,
    trade_name,
    dosage_form,
    -- Dosage groups: first match wins, same order and patterns as DOSAGE_GROUPS in clean.py.
    CASE
        WHEN regexp_matches(lower(dosage_form), 'inject|infusion|intravenous|parenteral')                     THEN 'injection_infusion'
        WHEN regexp_matches(lower(dosage_form), 'eye|ophthalm|intraocular')                                   THEN 'ophthalmic'
        WHEN regexp_matches(lower(dosage_form), 'tablet|caplet|lozenge')                                      THEN 'tablet'
        WHEN regexp_matches(lower(dosage_form), 'capsule')                                                    THEN 'capsule'
        WHEN regexp_matches(lower(dosage_form), 'inhal|nasal|spray|aerosol|nebul')                            THEN 'inhaled_nasal'
        WHEN regexp_matches(lower(dosage_form), 'cream|ointment|gel|lotion|topical|cutaneous|patch|plaster|shampoo|paste') THEN 'topical'
        WHEN regexp_matches(lower(dosage_form), 'oral|syrup|suspension|solution|drops|sachet|granules|powder') THEN 'oral_liquid'
        ELSE 'other'
    END                                                                         AS dosage_group,
    price,
    ln(price)                                                                   AS log_price,
    strength_raw,
    strength_parse_ok,
    CASE WHEN strength_parse_ok
         THEN CAST(string_split(regexp_replace(strength_norm, '[\s\pZ\x{85}]+', '', 'g'), ',')[1] AS DOUBLE)
    END                                                                         AS strength_first,
    CASE WHEN strength_parse_ok
         THEN len(string_split(regexp_replace(strength_norm, '[\s\pZ\x{85}]+', '', 'g'), ','))
    END                                                                         AS n_strength_values,
    ingredients,
    ingredients[1]                                                              AS first_ingredient,
    len(ingredients)                                                            AS n_ingredients,
    len(ingredients) > 1                                                        AS is_combo,
    strength_parse_ok AND len(string_split(regexp_replace(strength_norm, '[\s\pZ\x{85}]+', '', 'g'), ',')) = len(ingredients)
                                                                                AS strength_matches_ingredients,
    -- Rule 6: gene / cell therapy markers in the scientific name (flagged, not dropped).
    regexp_matches(molecule, 'leucel|temcel|parvovec|tagene|\bgene\b|\w+vec\b|\w+cel\b')
                                                                                AS is_advanced_therapy
FROM parsed
ORDER BY rn;
