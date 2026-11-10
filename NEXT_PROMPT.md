I'm a Dubai-based data analyst job seeker (B.E. Biotechnology, ~1.5 yrs experience) targeting healthcare analytics, pharma market access and medical insurance analyst roles in the UAE and KSA. This project (SFDA drug price analysis) is finished. Its results are in `reports/REPORT.md` and `reports/*.json|csv`. I want one small upgrade, because almost every job description I target screens for SQL, and this repo currently does everything in pandas.

Read `README.md`, `my_README.md`, `reports/REPORT.md`, and everything in `src/` and `tests/` before changing anything.

## Task: add a SQL (DuckDB) layer that reproduces the cleaning and the headline aggregates

1. Create `sql/` with numbered DuckDB SQL files that run on `data/clean/list_raw_parsed.csv` (or whichever parsed file `clean.py` reads; check):
   - `01_clean.sql`: the same cleaning rules as `src/clean.py` (dedupe repeated register numbers, drop missing or non-positive prices, flag gene and cell therapies). Write the output to a DuckDB table.
   - `02_data_quality.sql`: rebuild the counts in `reports/data_quality.csv` (rows in, rows dropped by reason, rows out).
   - `03_aggregates.sql`: the analyst-style views a pricing team would query: products and median price by dosage group; number of competing registrations per molecule; the like-for-like unbranded vs brand-named price ratio per (molecule, form, strength) cell. Use CTEs and window functions where they are the natural tool, not for show.
2. Add `src/run_sql.py` that runs the files in order against a local `data/clean/sfda.duckdb` and exports the views to CSV in `reports/sql/`.
3. Add a pytest file that checks the SQL output **matches the pandas output**: same `rows_out`, same drop counts, same number of ratio cells (247), and a median ratio equal within rounding. If they don't match, find out why and report it to me. Don't quietly change either side to force a match.
4. Add `duckdb` to `requirements.txt`, add the SQL step to the "Reproduce" section of `REPORT.md` and `my_README.md`, and add one line to the README results saying the cleaning is reproduced in SQL and reconciled with the Python pipeline.

## Rules
- Don't change any reported number unless the reconciliation shows a real bug. If it does, tell me first.
- Raw data stays local and unpublished (see `reports/scraping_notes.md`). Don't commit `data/`.
- Keep it small: about 1 day of work. No dashboards, no new analysis.
- At the end, run `pytest` and show me the result, plus a one-line resume bullet I could add, using only numbers that actually came out of the run.
