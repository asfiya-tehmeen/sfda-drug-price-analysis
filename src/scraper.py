"""Throttled, cached scraper for the SFDA drugs list pages.

Usage (from project root, venv active):
    python src/scraper.py --start 0 --end 3        # test: pages 0,1,2
    python src/scraper.py                          # full run, all pages

Raw HTML is saved to data/raw/list_page_NNNN.html and never overwritten.
Re-running skips pages already saved, so an interrupted run can resume.
"""
import argparse
import csv
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_URL = "https://www.sfda.gov.sa/en/drugs-list"
LAST_PAGE = 459  # 460 pages, 0-based; confirm on the site before a full run
RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
LOG_PATH = RAW_DIR / "scrape_log.csv"
USER_AGENT = "Academic-research-scraper (personal portfolio analysis; low rate)"
DELAY_SECONDS = 2.5
JITTER = 0.5
MAX_RETRIES = 4
TIMEOUT = 30


def page_path(n: int) -> Path:
    return RAW_DIR / f"list_page_{n:04d}.html"


def log(page: int, status: str, detail: str = "") -> None:
    new = not LOG_PATH.exists()
    with LOG_PATH.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp_utc", "page", "status", "detail"])
        w.writerow([datetime.now(timezone.utc).isoformat(), page, status, detail])


def fetch(session: requests.Session, n: int) -> str | None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.get(BASE_URL, params={"page": n}, timeout=TIMEOUT)
            if r.status_code == 200:
                if "details_data" in r.text:  # a real page has Details links
                    return r.text
                # HTTP 200 but "No Results Found": transient server glitch, do not cache
                log(n, "empty_page", f"attempt={attempt}")
                time.sleep(10 * attempt)
                continue
            log(n, "http_error", f"status={r.status_code} attempt={attempt}")
            if r.status_code in (403, 429):
                time.sleep(60 * attempt)  # back off hard if blocked or rate limited
        except requests.RequestException as e:
            log(n, "request_error", f"{type(e).__name__} attempt={attempt}")
        time.sleep(DELAY_SECONDS * 2 ** attempt)
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=LAST_PAGE + 1, help="exclusive")
    args = ap.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    fetched = skipped = failed = 0
    for n in range(args.start, args.end):
        path = page_path(n)
        if path.exists():
            skipped += 1
            continue
        html = fetch(session, n)
        if html is None:
            failed += 1
            log(n, "gave_up")
        else:
            path.write_text(html, encoding="utf-8")
            fetched += 1
            log(n, "ok", f"bytes={len(html)}")
            print(f"page {n}: saved")
        time.sleep(DELAY_SECONDS + random.uniform(0, JITTER))

    print(f"scrape date (UTC): {datetime.now(timezone.utc).date()}")
    print(f"fetched={fetched} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    main()
