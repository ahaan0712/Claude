#!/usr/bin/env python3
"""Part 2 — real posting ingestion.

Legitimate posting sources for this use case:
  (1) public crowdsourced Summer-2027 trackers on GitHub, and
  (2) direct company career pages (JobPosting JSON-LD) for higher tiers.
DOL disclosure data is sponsorship history, NOT postings, and is handled
separately in dol_lookup.py.

Every posting is tagged with its source. De-duplication is by
company+role-family+month rather than exact string match, because the same
role appears with slightly different titles across boards.

Failure handling (Part 3 audit requirement): a failed fetch is recorded as a
source error and NEVER silently presented as "no postings". If every source
fails, the stage raises instead of writing an empty file over good data.
"""
from __future__ import annotations
import json, re, urllib.request, urllib.error, datetime as dt
from pathlib import Path
from schema import write_json, now_iso
from companies import normalize_name

TRACKERS = [
    {"name": "vanshb03/Summer2027-Internships", "kind": "json",
     "url": "https://raw.githubusercontent.com/vanshb03/Summer2027-Internships/dev/.github/scripts/listings.json"},
    {"name": "sndsh404/summer-2027-internships", "kind": "md_table",
     "url": "https://raw.githubusercontent.com/sndsh404/summer-2027-internships/main/README.md"},
]
UA = {"User-Agent": "campaign27-ingest/1.0"}
INTERN = re.compile(r"\bintern|\binternship|co-?op", re.I)


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def ts_to_date(ts):
    try:
        return dt.datetime.utcfromtimestamp(int(ts)).strftime("%Y-%m-%d")
    except Exception:
        return None


def from_vansh(raw):
    out = []
    for x in json.loads(raw):
        title = (x.get("title") or "").strip()
        if not title or not INTERN.search(title):
            continue
        if not x.get("active", True) or not x.get("is_visible", True):
            continue
        locs = x.get("locations") or []
        out.append({
            "company": (x.get("company_name") or "").strip(),
            "title": title,
            "location": ", ".join(locs) if isinstance(locs, list) else str(locs),
            "posting_date": ts_to_date(x.get("date_posted")),
            "apply_url": x.get("url") or "",
            "sponsorship_hint": x.get("sponsorship") or "",
            "source": "tracker:vanshb03",
            "season": x.get("season") or "",
        })
    return out


def from_md_table(raw):
    out = []
    for line in raw.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5 or cells[0].lower() in ("company", "---") \
                or set(cells[0]) <= set("-: "):
            continue
        company, role, loc, apply_c, added = cells[0], cells[1], cells[2], \
            cells[3], cells[4]
        if not INTERN.search(role):
            continue
        m = re.search(r"\((https?://[^)]+)\)", apply_c)
        d = re.search(r"20\d\d-\d\d-\d\d", added)
        out.append({
            "company": company, "title": role, "location": loc,
            "posting_date": d.group(0) if d else None,
            "apply_url": m.group(1) if m else "",
            "sponsorship_hint": "", "source": "tracker:sndsh404", "season": "",
        })
    return out


def dedup(rows):
    """Dedup by company + role-family-ish token + month. Keep richest record."""
    def role_key(t):
        t = t.lower()
        t = re.sub(r"summer\s*20\d\d|20\d\d|\(.*?\)|intern(ship)?|-|,", " ", t)
        toks = [w for w in re.sub(r"[^a-z ]", " ", t).split() if len(w) > 2]
        return " ".join(sorted(set(toks)))

    best = {}
    for r in rows:
        month = (r.get("posting_date") or "")[:7]
        k = (normalize_name(r.get("company", "")), role_key(r.get("title", "")),
             month)
        cur = best.get(k)
        score = sum(1 for v in r.values() if v)
        if not cur or score > cur[0]:
            merged = dict(r)
            if cur:
                merged.setdefault("also_seen_in", [])
                srcs = set(cur[1].get("also_seen_in", []) + [cur[1]["source"]])
                merged["also_seen_in"] = sorted(srcs - {merged["source"]})
            best[k] = (score, merged)
        else:
            cur[1].setdefault("also_seen_in", [])
            if r["source"] not in cur[1]["also_seen_in"] \
                    and r["source"] != cur[1]["source"]:
                cur[1]["also_seen_in"].append(r["source"])
    return [v[1] for v in best.values()]


def main():
    rows, errors, source_stats = [], [], {}
    for t in TRACKERS:
        try:
            raw = fetch(t["url"])
            got = from_vansh(raw) if t["kind"] == "json" else from_md_table(raw)
            rows += got
            source_stats[t["name"]] = len(got)
        except Exception as e:  # network / parse failure — surface, never hide
            errors.append({"source": t["name"], "error": repr(e)})
            source_stats[t["name"]] = "FETCH_FAILED"

    if not rows and errors:
        raise SystemExit(f"FATAL: all posting sources failed: {errors}")

    deduped = dedup(rows)
    write_json("data/postings_raw.json", {
        "generated_at": now_iso(),
        "sources": source_stats,
        "source_errors": errors,
        "raw_count": len(rows),
        "deduped_count": len(deduped),
        "postings": deduped,
    })
    print(f"ingest: raw={len(rows)} deduped={len(deduped)} "
          f"sources={source_stats} errors={len(errors)}")


if __name__ == "__main__":
    main()
