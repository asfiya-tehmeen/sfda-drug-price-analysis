import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parse import parse_html  # noqa: E402

SAMPLE = """
<table><thead><tr><th>Scientific Name</th></tr></thead><tbody>
<tr class="odd"><td>SODIUM CHLORIDE</td><td>0.9% W/V SODIUM CHLORIDE B.P</td><td>0.9</td>
<td>Solution for injection</td><td>0.75</td>
<td><a href="/en/details_data?nid=17582&amp;id=1807245616&amp;page=0">Details</a></td></tr>
<tr class="even"><td>SODIUM CHLORIDE,POTASSIUM CHLORIDE</td><td>ORS New (50 SACHET)</td>
<td>0.52,0.3</td><td>Powder for oral solution in sachet</td><td>30.3</td>
<td><a href="/en/details_data?nid=17582&amp;id=1-585-09&amp;page=0">Details</a></td></tr>
<tr><td>BROKEN ROW</td></tr>
</tbody></table>
"""


def test_parses_rows_and_skips_malformed():
    rows = parse_html(SAMPLE, page=0)
    assert len(rows) == 2


def test_fields_and_register_no():
    r = parse_html(SAMPLE, page=7)[0]
    assert r["scientific_name"] == "SODIUM CHLORIDE"
    assert r["price"] == "0.75"
    assert r["register_no"] == "1807245616"
    assert r["page"] == 7


def test_combination_strength_kept_raw():
    assert parse_html(SAMPLE)[1]["strength"] == "0.52,0.3"
    assert parse_html(SAMPLE)[1]["register_no"] == "1-585-09"


def test_empty_page():
    assert parse_html("<html></html>") == []


@pytest.mark.skipif(not (ROOT / "data/raw/list_page_0000.html").exists(), reason="no cached page")
def test_real_page_has_20_rows():
    html = (ROOT / "data/raw/list_page_0000.html").read_text(encoding="utf-8")
    assert len(parse_html(html, 0)) == 20
