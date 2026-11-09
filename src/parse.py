"""Parse cached SFDA list pages (data/raw/list_page_NNNN.html) into one table.

No cleaning happens here: every field is kept as the raw string from the page.
Cleaning lives in clean.py.

Usage (from project root):
    python src/parse.py            # writes data/clean/list_raw_parsed.csv
"""
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUT_PATH = ROOT / "data" / "clean" / "list_raw_parsed.csv"

COLUMNS = ["scientific_name", "trade_name", "strength", "dosage_form", "price"]


def parse_html(html: str, page: int | None = None) -> list[dict]:
    """Return one dict per drug row on a list page."""
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if table is None or table.find("tbody") is None:
        return []
    rows = []
    for tr in table.find("tbody").find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) != 6:
            continue  # unexpected layout: skip, caller counts via page totals
        row = dict(zip(COLUMNS, (td.get_text(strip=True) for td in tds[:5])))
        link = tds[5].find("a")
        href = link["href"] if link and link.has_attr("href") else ""
        row["register_no"] = parse_qs(urlparse(href).query).get("id", [""])[0]
        row["page"] = page
        rows.append(row)
    return rows


def page_number(path: Path) -> int:
    return int(re.search(r"list_page_(\d+)\.html$", path.name).group(1))


def parse_all(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    records = []
    for path in sorted(raw_dir.glob("list_page_*.html")):
        records += parse_html(path.read_text(encoding="utf-8"), page_number(path))
    return pd.DataFrame(records, columns=COLUMNS + ["register_no", "page"])


if __name__ == "__main__":
    df = parse_all()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_PATH, index=False, encoding="utf-8")
    print(f"pages={df['page'].nunique()} rows={len(df)} -> {OUT_PATH}")
