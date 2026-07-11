#!/usr/bin/env python3
"""
Campaign 27 V7 - dol_lookup.py

Pulls real H-1B/LCA (Labor Condition Application) filing counts per company
from public sources, so score.py's eligibility gate can stop guessing a
default CPT-friendliness score and instead say "this company has N real LCA
filings over the last 3 fiscal years, trend X" or "no filing history found -
rely on exact posting language."

Primary source: DOL OFLC's public LCA Disclosure Data files
(https://www.dol.gov/agencies/eta/foreign-labor/performance). These are
published per fiscal-year quarter, are not cumulative across quarters, and
ship as .xlsx (occasionally .csv in older years) - no API key, no auth, no
rate limit, but large (tens-to-hundreds of MB per quarter). This script
streams each file from disk rather than loading it fully into memory, and
tallies matches for every tracked company in a single pass per file rather
than re-downloading per company.

Fallback source: h1bdata.info, queried per company, for any company the DOL
bulk pass found zero rows for (or for every company if the DOL files
couldn't be fetched at all - e.g. DOL renamed/moved a URL, or the file
layout changed). h1bdata.info is a third-party convenience site built on the
same DOL disclosure data; it is used only to fill gaps, never preferred over
the primary source.

Company matching reuses companies.py's normalize_name()/names_match() - the
one alias table this project uses to bridge "Capital One" (posting board) to
"Capital One, National Association" (DOL employer legal name), rather than
maintaining a second copy of that logic here or in app.html.

Network reality check: DOL's file layout and exact URLs change over time
without notice (quarters get renamed, hosts move between dol.gov and
foreignlaborcert.doleta.gov, some years shipped .csv instead of .xlsx). This
script tries several known URL patterns per fiscal-year-quarter and treats a
failure to fetch as exactly that - a failure - never as evidence of "no
filings." See sponsorship_evidence: "UNKNOWN" below.

Honesty rule, matching the rest of this project: sponsorship_evidence is
only ever "REAL" (we successfully reached a source and found >=1 filing),
"NONE" (we successfully reached a source and found zero filings), or
"UNKNOWN" (we could not reach any source for this company - never silently
treated as NONE). No count is ever fabricated to fill a gap.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))
from companies import names_match, normalize_name  # noqa: E402

USER_AGENT = "campaign-27-v7-dol-lookup/1.0 (educational job-search tool; contact via github issue)"
REQUEST_TIMEOUT = 60
MAX_RETRIES = 3

# Well-known large employers already present on the ingested posting board
# (data/postings.json) that fit Ahaan's analytics/econ-consulting target
# profile. This repo does not have a "157-company board" file or a company
# tier field - V7 deliberately removed company-level ranking (see README).
# This list exists only so the DOL/h1bdata pull can be sanity-checked against
# a fixed, named set of companies expected to have real public LCA history;
# it is not surfaced anywhere as a ranking.
STRONG_TARGET_COMPANIES = [
    "Capital One", "JPMorganChase", "Citi", "Bank of America", "BlackRock",
    "BNP Paribas", "DTCC", "Fiserv", "Salesforce", "Microsoft", "Amazon",
    "Databricks", "Twilio",
]

DOL_BASE_URLS = [
    "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs",
    "https://www.foreignlaborcert.doleta.gov/pdf",
]
DOL_QUARTERS = ["Q4", "Q3", "Q2", "Q1"]


def federal_fiscal_year(d: date) -> int:
    return d.year + 1 if d.month >= 10 else d.year


def target_fiscal_years(as_of: date, n: int = 3) -> List[int]:
    current = federal_fiscal_year(as_of)
    return [current - n + 1 + i for i in range(n)]


def _is_non_retryable(exc: Exception) -> bool:
    """403/Forbidden (e.g. a network-policy proxy blocking the host outright)
    won't succeed on retry - only sleep-and-retry for genuinely transient
    errors (timeouts, DNS blips, 5xx)."""
    msg = str(exc)
    return "403" in msg or "Forbidden" in msg


def http_get(url: str, timeout: int = REQUEST_TIMEOUT) -> Optional[bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            last_error = exc
            if _is_non_retryable(exc):
                break
            if attempt < MAX_RETRIES:
                time.sleep(2 * attempt)
    print(f"  ! fetch failed for {url}: {last_error}", file=sys.stderr)
    return None


def http_get_to_tempfile(url: str) -> Optional[Path]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                fd, tmp_path = tempfile.mkstemp(suffix=".bin")
                with open(fd, "wb") as out:
                    while True:
                        chunk = resp.read(1 << 20)
                        if not chunk:
                            break
                        out.write(chunk)
                return Path(tmp_path)
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            last_error = exc
            if _is_non_retryable(exc):
                break
            if attempt < MAX_RETRIES:
                time.sleep(2 * attempt)
    print(f"  ! fetch failed for {url}: {last_error}", file=sys.stderr)
    return None


def _col_letters_to_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref).group(0)
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def load_shared_strings(z: zipfile.ZipFile) -> List[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    shared = []
    with z.open("xl/sharedStrings.xml") as f:
        for _, elem in ET.iterparse(f):
            tag = elem.tag.split("}")[-1]
            if tag == "si":
                text = "".join(t.text or "" for t in elem.iter() if t.tag.split("}")[-1] == "t")
                shared.append(text)
                elem.clear()
    return shared


def iter_xlsx_rows(path: Path, sheet: str = "xl/worksheets/sheet1.xml"):
    """Yields each row of the first worksheet as a list of cell strings, in
    column order, using only stdlib (zipfile + ElementTree) - the disclosure
    files are simple flat tables, so a full spreadsheet engine isn't needed."""
    with zipfile.ZipFile(path) as z:
        shared = load_shared_strings(z)
        with z.open(sheet) as f:
            row_cells: Dict[int, str] = {}
            for event, elem in ET.iterparse(f, events=("end",)):
                tag = elem.tag.split("}")[-1]
                if tag != "row":
                    continue
                row_cells.clear()
                for c in elem:
                    if c.tag.split("}")[-1] != "c":
                        continue
                    ref = c.get("r", "A1")
                    col_idx = _col_letters_to_index(ref)
                    cell_type = c.get("t")
                    value = ""
                    for child in c:
                        ctag = child.tag.split("}")[-1]
                        if ctag == "v":
                            value = child.text or ""
                        elif ctag == "is":
                            value = "".join(t.text or "" for t in child.iter() if t.tag.split("}")[-1] == "t")
                    if cell_type == "s" and value != "":
                        try:
                            value = shared[int(value)]
                        except (ValueError, IndexError):
                            value = ""
                    row_cells[col_idx] = value
                if row_cells:
                    width = max(row_cells) + 1
                    yield [row_cells.get(i, "") for i in range(width)]
                elem.clear()


def find_employer_column(header: List[str]) -> Optional[int]:
    candidates = {"employer_name", "employer (petitioner) name", "petitioner name", "employer"}
    for i, h in enumerate(header):
        if h.strip().lower() in candidates:
            return i
    for i, h in enumerate(header):
        if "employer" in h.strip().lower():
            return i
    return None


def tally_from_rows(rows_iter, companies: List[str], fy: int, tally: Dict[str, Dict[int, int]],
                     matched_names: Dict[str, set]) -> int:
    header = None
    employer_col = None
    row_count = 0
    for row in rows_iter:
        if header is None:
            header = row
            employer_col = find_employer_column(header)
            if employer_col is None:
                return 0
            continue
        if employer_col >= len(row):
            continue
        employer_name = row[employer_col]
        if not employer_name:
            continue
        row_count += 1
        for company in companies:
            if names_match(company, employer_name):
                tally[company][fy] += 1
                matched_names[company].add(employer_name)
    return row_count


def fetch_dol_quarter(base_url: str, fy: int, quarter: str) -> Optional[Path]:
    for ext in ("xlsx", "csv"):
        url = f"{base_url}/LCA_Disclosure_Data_FY{fy}_{quarter}.{ext}"
        path = http_get_to_tempfile(url)
        if path is not None:
            return path
    return None


def process_dol_fiscal_year(fy: int, companies: List[str], tally: Dict[str, Dict[int, int]],
                             matched_names: Dict[str, set]) -> Tuple[bool, int]:
    """Returns (reached, quarters_parsed). reached is True if at least one
    quarter file for this fiscal year was successfully fetched and parsed
    (i.e. the source was reachable), whether or not it happened to contain
    matches. quarters_parsed counts how many of the 4 quarters actually
    came back - DOL publishes each quarter with a lag of a few months, so
    the current/most recent fiscal year is often still incomplete. Callers
    use this to avoid comparing a complete year against a partial one and
    calling the difference a "trend"."""
    reached = False
    quarters_parsed = 0
    for quarter in DOL_QUARTERS:
        fetched = None
        for base_url in DOL_BASE_URLS:
            fetched = fetch_dol_quarter(base_url, fy, quarter)
            if fetched:
                break
        if fetched is None:
            continue
        try:
            if fetched.read_bytes()[:2] == b"PK":
                rows = tally_from_rows(iter_xlsx_rows(fetched), companies, fy, tally, matched_names)
            else:
                with fetched.open("r", encoding="utf-8", errors="replace", newline="") as f:
                    rows = tally_from_rows(csv.reader(f), companies, fy, tally, matched_names)
            if rows > 0:
                reached = True
                quarters_parsed += 1
                print(f"  FY{fy} {quarter}: parsed {rows} disclosure rows")
        except (zipfile.BadZipFile, ET.ParseError, csv.Error, UnicodeDecodeError) as exc:
            print(f"  ! could not parse FY{fy} {quarter} file: {exc}", file=sys.stderr)
        finally:
            fetched.unlink(missing_ok=True)
    return reached, quarters_parsed


H1BDATA_ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
H1BDATA_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")


def parse_h1bdata_html(html: str) -> List[Dict[str, str]]:
    rows = []
    for row_html in H1BDATA_ROW_RE.findall(html):
        cells = [TAG_RE.sub("", c).strip() for c in H1BDATA_CELL_RE.findall(row_html)]
        cells = [c for c in cells if c]
        if len(cells) < 5:
            continue
        rows.append({"employer": cells[0], "submit_date": cells[4] if len(cells) > 4 else ""})
    return rows


def h1bdata_lookup(company: str, fiscal_years: List[int]) -> Tuple[Optional[Dict[int, int]], bool, Optional[str]]:
    """Returns (per-fiscal-year counts or None, reached, matched employer name)."""
    url = "https://h1bdata.info/index.php?" + urllib.parse.urlencode(
        {"em": company, "job": "", "city": "", "year": "All Years"}
    )
    body = http_get(url)
    if body is None:
        return None, False, None
    html = body.decode("utf-8", errors="replace")
    rows = parse_h1bdata_html(html)
    if not rows:
        return {}, True, None

    fy_counts: Dict[int, int] = defaultdict(int)
    matched_employer = None
    for row in rows:
        if not names_match(company, row["employer"]):
            continue
        matched_employer = matched_employer or row["employer"]
        try:
            submit_date = datetime.strptime(row["submit_date"], "%m/%d/%Y").date()
        except ValueError:
            continue
        fy = federal_fiscal_year(submit_date)
        if fy in fiscal_years:
            fy_counts[fy] += 1
    return dict(fy_counts), True, matched_employer


QUARTERS_PER_FY = 4


def compute_trend(fy_counts: Dict[int, int], complete_fiscal_years: List[int]) -> str:
    """Trend is only ever computed between two fiscal years DOL has fully
    published (4/4 quarters) - never against the current/most recent FY
    while it's still partial. DOL publishes each quarter with a few months'
    lag, so the latest target fiscal year is routinely incomplete; comparing
    a complete year's total against a partial one would show "falling" for
    almost every employer near the start of a fiscal year, which is an
    artifact of publication lag, not a real signal. insufficient_data (not
    a guess) is the honest answer until 2+ complete years exist."""
    if len(complete_fiscal_years) < 2:
        return "insufficient_data"
    ordered = sorted(complete_fiscal_years)
    first, last = fy_counts.get(ordered[0], 0), fy_counts.get(ordered[-1], 0)
    if first == 0 and last == 0:
        return "insufficient_data"
    if first == 0:
        return "rising"
    ratio = last / first
    if ratio >= 1.15:
        return "rising"
    if ratio <= 0.85:
        return "falling"
    return "flat"


def load_companies(postings_path: Path) -> List[str]:
    payload = json.loads(postings_path.read_text(encoding="utf-8"))
    seen = {}
    for p in payload["postings"]:
        name = p["company"].strip()
        if name and normalize_name(name) not in seen:
            seen[normalize_name(name)] = name
    return sorted(seen.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--postings", default=Path("data/postings.json"), type=Path)
    parser.add_argument("--out", default=Path("data/dol_lookup.json"), type=Path)
    parser.add_argument("--as-of", default=None, help="YYYY-MM-DD, defaults to today (UTC).")
    parser.add_argument("--skip-dol-bulk", action="store_true",
                         help="Skip the large DOL bulk-file pass and go straight to h1bdata.info per company.")
    args = parser.parse_args()

    as_of = datetime.strptime(args.as_of, "%Y-%m-%d").date() if args.as_of else date.today()
    fiscal_years = target_fiscal_years(as_of)
    companies = load_companies(args.postings)
    print(f"Looking up {len(companies)} companies for fiscal years {fiscal_years}")

    tally: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
    matched_names: Dict[str, set] = defaultdict(set)
    dol_reachable = False
    fy_quarters_parsed: Dict[int, int] = {}

    if not args.skip_dol_bulk:
        for fy in fiscal_years:
            print(f"Fetching DOL LCA disclosure data for FY{fy} ...")
            reached, quarters_parsed = process_dol_fiscal_year(fy, companies, tally, matched_names)
            fy_quarters_parsed[fy] = quarters_parsed
            if reached:
                dol_reachable = True

    # A fiscal year only counts as "complete" for trend purposes once all 4
    # quarters have been published. h1bdata.info draws on the same
    # underlying DOL data, so it's subject to the same publication lag -
    # this completeness check applies regardless of which source a given
    # company's counts ultimately came from.
    complete_fiscal_years = [fy for fy in fiscal_years if fy_quarters_parsed.get(fy, 0) >= QUARTERS_PER_FY]
    if len(complete_fiscal_years) < len(fiscal_years):
        incomplete = [fy for fy in fiscal_years if fy not in complete_fiscal_years]
        print(f"Fiscal year(s) {incomplete} are not fully published yet "
              f"(quarters parsed: { {fy: fy_quarters_parsed.get(fy, 0) for fy in incomplete} }) - "
              "excluded from trend comparisons.")

    h1bdata_reachable_any = False
    companies_out = {}
    for company in companies:
        fy_counts = {fy: tally[company].get(fy, 0) for fy in fiscal_years}
        total = sum(fy_counts.values())
        source = "DOL_BULK" if total > 0 else None
        checked = dol_reachable

        if total == 0:
            h1b_counts, reached, matched_employer = h1bdata_lookup(company, fiscal_years)
            if reached:
                h1bdata_reachable_any = True
                checked = True
                if h1b_counts:
                    fy_counts = {fy: h1b_counts.get(fy, 0) for fy in fiscal_years}
                    total = sum(fy_counts.values())
                    if total > 0:
                        source = "H1BDATA_INFO"
                        if matched_employer:
                            matched_names[company].add(matched_employer)

        if not checked:
            evidence = "UNKNOWN"
        elif total > 0:
            evidence = "REAL"
        else:
            evidence = "NONE"

        companies_out[company] = {
            "company": company,
            "fiscal_year_filings": fy_counts,
            "total_filings_3yr": total,
            "trend": compute_trend(fy_counts, complete_fiscal_years) if checked else "insufficient_data",
            "sponsorship_evidence": evidence,
            "source": source,
            "matched_employer_names": sorted(matched_names.get(company, [])),
            "checked": checked,
        }

    payload = {
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "as_of_date": as_of.isoformat(),
        "target_fiscal_years": fiscal_years,
        "complete_fiscal_years": complete_fiscal_years,
        "fiscal_year_quarters_published": fy_quarters_parsed,
        "dol_bulk_reachable": dol_reachable,
        "h1bdata_fallback_reachable": h1bdata_reachable_any,
        "company_count": len(companies_out),
        "note": (
            "sponsorship_evidence is REAL or NONE only when a source was actually reached for that "
            "company (checked=true). UNKNOWN means neither DOL's bulk disclosure files nor "
            "h1bdata.info could be reached for this company - never treated as NONE. trend is "
            "'insufficient_data' unless at least 2 fiscal years in complete_fiscal_years (all 4 "
            "quarters published by DOL) are available - the most recent target fiscal year is "
            "routinely still partial due to DOL's publication lag, and comparing a complete year "
            "against a partial one would manufacture a false 'falling' signal for almost everyone."
        ),
        "companies": companies_out,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    real_count = sum(1 for c in companies_out.values() if c["sponsorship_evidence"] == "REAL")
    unknown_count = sum(1 for c in companies_out.values() if c["sponsorship_evidence"] == "UNKNOWN")
    print(f"Wrote {len(companies_out)} companies -> {args.out}")
    print(f"REAL: {real_count}  NONE: {len(companies_out) - real_count - unknown_count}  UNKNOWN: {unknown_count}")

    strong_target_real = [c for c in STRONG_TARGET_COMPANIES
                           if companies_out.get(c, {}).get("sponsorship_evidence") == "REAL"]
    print(f"Strong Target companies with REAL evidence: {len(strong_target_real)}/{len(STRONG_TARGET_COMPANIES)}")
    for c in STRONG_TARGET_COMPANIES:
        entry = companies_out.get(c)
        status = entry["sponsorship_evidence"] if entry else "NOT_ON_BOARD"
        print(f"  {c}: {status}")

    if not dol_reachable and not h1bdata_reachable_any:
        print(
            "WARNING: neither DOL nor h1bdata.info was reachable this run. All companies are UNKNOWN. "
            "This is expected in network-restricted sandboxes; run this script somewhere with outbound "
            "internet access (e.g. the dol-lookup.yml GitHub Actions workflow) to populate real data.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
