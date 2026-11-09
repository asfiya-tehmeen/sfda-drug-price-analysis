# Scraping notes: SFDA Drugs List

Date checked: 2026-11-09

## 1. robots.txt (https://sfda.gov.sa/robots.txt)
- `/en/drugs-list` is NOT disallowed.
- Disallowed paths are Drupal internals plus `/search/` and `/search?`. I will not request any URL containing those.
- No `Crawl-delay` set. I use my own throttle (see section 4).

## 2. Terms of use
- Terms of use: https://www.sfda.gov.sa/en/terms-of-use (last updated 26/07/2024)
- Rules of use: https://www.sfda.gov.sa/en/rules-of-use (last updated 26/07/2024)
- Neither page mentions scraping, crawling, bots or data mining.
- Relevant clauses:
  - Content is "available for your personal use".
  - Terms of use: "strictly forbidden to transfer copy or create links to the SFDA portal or any of its contents".
  - Rules of use: license to use the site "for internal business purposes only"; "data compilations, title lists" are SFDA property; copying or distributing outside the license needs prior written consent.
  - Prohibits actions imposing "an unreasonable or disproportionately large load" on the portal.
- Interpretation: unclear, not a clear ban. Copying and redistribution language is strict, so the raw data will not be republished.
- I am not a lawyer; this is not legal advice.

## 3. Decision
Proceed conservatively, for private analysis only:
- Throttled requests, every page cached, no repeat requests.
- Raw data stays local (`data/raw/` is not published or committed). Only aggregated findings and code are shared.
- Send an Ask SFDA request (https://www.sfda.gov.sa/en/form/ask-sfda) asking for a dataset or permission for research use.
  - Sent on: 2026-11-09  Reply: ____
- If SFDA objects or refuses, stop and delete the scraped data.

## 4. Scraper behaviour
- 1 request every 2.5 s (plus small random jitter), identifying User-Agent, retries with backoff.
- Pages saved to `data/raw/list_page_NNNN.html`; existing files are skipped.
- Failures logged to `data/raw/scrape_log.csv`.

## 5. Site findings
- List URL: `https://www.sfda.gov.sa/en/drugs-list?page=N`, N is 0-based, 0 to 459 (460 pages).
- 20 rows per page, so about 9,200 rows (estimate; the site shows no total).
- Rows are in static HTML (server-rendered). Columns: Scientific Name, Trade Name, Strength, "Doesage Form" (sic), Price, Details.
- Combination products: one cell, comma-separated (e.g. strength `0.52,0.3,0.58,2.7`).
- Detail link: `/en/details_data?nid=17582&id=<ID>&page=0`. ID formats vary (e.g. `1807245616`, `1-585-09`).
- Detail page: shows full record in a browser (register no., strength unit, size/unit, package type/size, manufacturers, ATC codes, legal status, marketing status), but the static HTML has an empty `<tbody class="attachmentstr">`. Network tab showed only feedback-widget and analytics calls, no data call. Not obtainable with plain `requests`.
- SCOPE DECISION (2026-11-09): list pages only. Detail pages are out of scope unless SFDA replies with a dataset or permission. Consequences: no manufacturer, ATC, strength unit or pack size; units and pack size must be parsed from list text, and the manufacturer term is dropped from the hedonic model.
- Filters (Trade Name, Scientific Name, Agent, Manufacturer Name, Reg No) are not used.
- Site shows a "Beta version" label, so the layout may change. Raw HTML is cached so parsing can be redone.

## 6. Scrape log
| Item | Value |
|---|---|
| Scrape date | 2026-11-09 |
| Pages requested | 460 (page=0 to 459) |
| Pages with data | 413 |
| Pages returning "No Results Found" | 47 (about 10%); not recovered after 4 retries each, so re-fetching was stopped to avoid extra load |
| Rows parsed | 8,246 (8,172 unique register numbers) |
| Hard failures (HTTP/connection) | 1 transient ConnectionError (page 200), recovered on retry |

Missing pages (0-based): 7, 12, 13, 15, 16, 17, 18, 19, 21, 22, 23, 25, 27, 40, 47, 57, 60, 67, 75, 76, 83, 94, 106, 108, 110, 111, 115, 116, 120, 123, 126, 127, 128, 134, 192, 198, 202, 203, 205, 207, 225, 229, 230, 293, 436, 442, 446.

Limitation to state in the report: about 900 products (roughly 10%) are absent. The gaps cluster in the earlier pages (36 of 47 are below page 135), and the page ordering is not known to be random, so the bias direction is unknown. Compare against SFDA's own count if available.

Note: the first full run cached these "No Results" pages as successes (scraper bug, fixed to reject pages without Details links). Bad files were deleted before re-fetching.
