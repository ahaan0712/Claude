#!/usr/bin/env python3
"""
Campaign 27 V7 - ingest.py

Pulls Summer 2027 internship postings from public GitHub trackers and caches
them to data/postings.json. Also accepts a paste-in path for rows copied
directly out of Simplify (which has no scrapable public API).

Sources (README markdown tables, fetched raw):
  - vanshb03/Summer2027-Internships
  - sndsh404/summer-2027-internships

Both trackers mark postings with badge emoji in the Company/Role cell:
  🛂 = no visa sponsorship      🇺🇸 = US citizens only      🔒 = closed/applications shut

Nothing here computes fit or eligibility - this script only fetches, parses,
normalizes, and deduplicates postings. Scoring happens in score.py.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

TRACKER_SOURCES = {
    "vanshb03/Summer2027-Internships": [
        "https://raw.githubusercontent.com/vanshb03/Summer2027-Internships/dev/README.md",
        "https://raw.githubusercontent.com/vanshb03/Summer2027-Internships/main/README.md",
    ],
    "sndsh404/summer-2027-internships": [
        "https://raw.githubusercontent.com/sndsh404/summer-2027-internships/main/README.md",
    ],
}

BADGE_NO_SPONSORSHIP = "\U0001F6C2"  # 🛂
BADGE_US_CITIZEN = "\U0001F1FA\U0001F1F8"  # 🇺🇸
BADGE_CLOSED = "\U0001F512"  # 🔒

USER_AGENT = "campaign-27-v7-ingest/1.0 (+https://github.com/)"


def fetch_url(url: str, timeout: int = 20) -> Optional[str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        print(f"  ! fetch failed for {url}: {exc}", file=sys.stderr)
        return None


def fetch_readme(source: str, urls: List[str]) -> Optional[str]:
    for url in urls:
        text = fetch_url(url)
        if text:
            print(f"  fetched {source} from {url} ({len(text)} bytes)")
            return text
    return None


def strip_html(cell: str) -> str:
    """Remove HTML tags and markdown link syntax, keeping link URLs and visible text."""
    links = re.findall(r'href="([^"]+)"', cell)
    links += re.findall(r"\[[^\]]*\]\((\S+?)\)", cell)
    cell = re.sub(r"\[([^\]]*)\]\(\S+?\)", r"\1", cell)  # markdown link -> just its text
    cell = re.sub(r"<[^>]+>", " ", cell)
    cell = html.unescape(cell)
    cell = re.sub(r"\s+", " ", cell).strip()
    return cell, links


def extract_markdown_link(cell: str) -> Optional[str]:
    m = re.search(r"\[[^\]]*\]\((\S+?)\)", cell)
    return m.group(1) if m else None


TODAY_YEAR = datetime.utcnow().year


def parse_date_cell(cell: str) -> Optional[str]:
    cell = cell.strip()
    if not cell or cell in {"-", "—", "–"}:
        return None
    # ISO: 2026-07-08
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", cell)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # "Jul 09" style (no year given -> assume current year, or prior if in future)
    m = re.match(r"([A-Za-z]{3})\s+(\d{1,2})", cell)
    if m:
        month_str, day_str = m.group(1), m.group(2)
        try:
            parsed = datetime.strptime(f"{month_str} {day_str} {TODAY_YEAR}", "%b %d %Y").date()
            if parsed > date.today():
                parsed = parsed.replace(year=TODAY_YEAR - 1)
            return parsed.isoformat()
        except ValueError:
            return None
    return None


def detect_badges(raw_cell: str) -> Dict[str, bool]:
    return {
        "no_sponsorship_badge": BADGE_NO_SPONSORSHIP in raw_cell,
        "us_citizen_badge": BADGE_US_CITIZEN in raw_cell,
        "closed_badge": BADGE_CLOSED in raw_cell,
    }


def parse_markdown_table(md_text: str, source: str) -> List[dict]:
    """
    Generic parser for the 5-column trackers:
      Company | Role | Location | Apply/Link | Date
    Tolerates HTML-in-cell (details/summary/br/img/a) and markdown-link cells.
    Carries the company name forward for continuation rows (blank/'↳' company cell,
    used by trackers to list multiple roles under one company).
    """
    postings = []
    last_company = None
    lines = md_text.splitlines()

    for line in lines:
        line = line.rstrip()
        if not line.startswith("|"):
            continue
        # skip separator rows like |---|---|---|
        if re.match(r"^\|[\s:|\-]+\|$", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        header_like = {c.lower() for c in cells}
        if header_like & {"company", "role", "location", "apply", "date posted", "added", "application/link"}:
            continue

        company_raw, role_raw = cells[0], cells[1]
        location_raw = cells[2] if len(cells) > 2 else ""
        apply_raw = cells[3] if len(cells) > 3 else ""
        date_raw = cells[4] if len(cells) > 4 else ""

        badges = detect_badges(company_raw + " " + role_raw + " " + apply_raw)

        company, _ = strip_html(company_raw)
        company = re.sub(r"[\U0001F300-\U0001FAFF☀-➿]", "", company).strip()
        if company in {"", "↳", "-"}:
            company = last_company or ""
        else:
            last_company = company
        if not company:
            continue

        role, _ = strip_html(role_raw)
        role = re.sub(r"[\U0001F300-\U0001FAFF☀-➿]", "", role).strip()

        location, _ = strip_html(location_raw)

        url = extract_markdown_link(apply_raw)
        if not url:
            _, links = strip_html(apply_raw)
            url = links[0] if links else None

        date_posted = parse_date_cell(strip_html(date_raw)[0])

        if not role or role.lower() in {"role", ""}:
            continue

        posting_id = f"{source}:{company}:{role}:{location}".lower()
        posting_id = re.sub(r"\s+", " ", posting_id).strip()

        postings.append({
            "posting_id": posting_id,
            "source": source,
            "company": company,
            "role": role,
            "location": location,
            "url": url,
            "date_posted": date_posted,
            "no_sponsorship_badge": badges["no_sponsorship_badge"],
            "us_citizen_badge": badges["us_citizen_badge"],
            "closed_badge": badges["closed_badge"],
        })

    return postings


def parse_paste_in(path: Path) -> List[dict]:
    """
    Paste-in path for Simplify rows. Accepts either:
      - tab-separated rows copied straight out of the Simplify table
        (Company \t Role \t Location \t Date \t ...)
      - lines of 'Company | Role | Location | URL | Date'
    One row per line. Blank lines and a header row are ignored.
    """
    if not path.exists():
        return []
    postings = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.lower().startswith("company"):
            continue
        if "\t" in line:
            parts = [p.strip() for p in line.split("\t")]
        else:
            parts = [p.strip() for p in line.split("|")]
        parts = [p for p in parts if p != ""] if len(parts) < 2 else parts
        if len(parts) < 2:
            continue
        company = parts[0]
        role = parts[1]
        location = parts[2] if len(parts) > 2 else ""
        rest = " ".join(parts[3:])
        url = extract_markdown_link(rest)
        if not url:
            m = re.search(r"https?://\S+", rest)
            url = m.group(0) if m else None
        date_posted = None
        for p in parts[3:]:
            d = parse_date_cell(p)
            if d:
                date_posted = d
                break
        badges = detect_badges(line)
        posting_id = f"simplify-paste:{company}:{role}:{location}".lower()
        postings.append({
            "posting_id": re.sub(r"\s+", " ", posting_id).strip(),
            "source": "simplify-paste",
            "company": company,
            "role": role,
            "location": location,
            "url": url,
            "date_posted": date_posted,
            "no_sponsorship_badge": badges["no_sponsorship_badge"],
            "us_citizen_badge": badges["us_citizen_badge"],
            "closed_badge": badges["closed_badge"],
        })
    return postings


def dedupe(postings: List[dict]) -> List[dict]:
    seen = {}
    for p in postings:
        key = (p["company"].strip().lower(), p["role"].strip().lower())
        if key not in seen:
            seen[key] = p
        else:
            existing = seen[key]
            if p.get("url") and not existing.get("url"):
                existing["url"] = p["url"]
            if p.get("date_posted") and not existing.get("date_posted"):
                existing["date_posted"] = p["date_posted"]
            existing["no_sponsorship_badge"] = existing["no_sponsorship_badge"] or p["no_sponsorship_badge"]
            existing["us_citizen_badge"] = existing["us_citizen_badge"] or p["us_citizen_badge"]
            existing["closed_badge"] = existing["closed_badge"] or p["closed_badge"]
    return list(seen.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=Path("data/postings.json"), type=Path)
    parser.add_argument("--paste-in", default=Path("data/simplify_paste.txt"), type=Path,
                         help="Text file of rows pasted from Simplify (optional).")
    parser.add_argument("--no-fetch", action="store_true",
                         help="Skip network fetch, use only the paste-in file plus existing cache.")
    args = parser.parse_args()

    all_postings: List[dict] = []

    if not args.no_fetch:
        for source, urls in TRACKER_SOURCES.items():
            print(f"Fetching {source} ...")
            text = fetch_readme(source, urls)
            if text is None:
                print(f"  ! could not fetch {source}, skipping this run (cache untouched for this source)")
                continue
            parsed = parse_markdown_table(text, source)
            print(f"  parsed {len(parsed)} rows")
            all_postings.extend(parsed)
    else:
        print("Skipping network fetch (--no-fetch).")

    if args.paste_in.exists():
        pasted = parse_paste_in(args.paste_in)
        print(f"Parsed {len(pasted)} rows from paste-in file {args.paste_in}")
        all_postings.extend(pasted)

    # merge with existing cache so a failed fetch doesn't wipe prior data
    existing = []
    if args.out.exists():
        try:
            cached = json.loads(args.out.read_text(encoding="utf-8"))
            existing = cached.get("postings", [])
        except (json.JSONDecodeError, OSError):
            existing = []

    merged = dedupe(existing + all_postings)
    merged.sort(key=lambda p: (p.get("date_posted") or "", p["company"]), reverse=True)

    payload = {
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "sources": list(TRACKER_SOURCES.keys()) + ["simplify-paste"],
        "posting_count": len(merged),
        "postings": merged,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(merged)} postings to {args.out}")


if __name__ == "__main__":
    main()
