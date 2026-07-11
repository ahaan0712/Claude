#!/usr/bin/env python3
"""
Campaign 27 V7 - companies.py

Shared company-name normalization + alias table. dol_lookup.py uses this to
match the free-text company names on tracker postings (data/postings.json)
against DOL LCA employer legal names; score.py uses the same normalize_name()
so a posting's "company" field and dol_lookup.json's "company" key always
line up. One table, reused everywhere a company name is compared - not
reimplemented per file.

Matching strategy:
  1. normalize_name() strips legal suffixes (Inc, LLC, Corp, N.A., ...),
     punctuation, and case.
  2. If either normalized name is a substring of the other AND the shorter
     one is >=6 characters, treat it as a match. Below 6 characters a
     substring match is unreliable ("Neo" would match thousands of unrelated
     employer names in a DOL disclosure file), so short/ambiguous company
     names only match through an explicit ALIASES entry.
  3. ALIASES maps a posting-board company name straight to the DOL employer
     legal name (or name fragment) it should be searched for, for companies
     where the two names diverge too much for normalization to bridge
     (JPMorganChase -> "JPMorgan Chase", DTCC -> the full legal name, etc.)
     or where the short-name guard in (2) would otherwise block a real
     match.
"""

from __future__ import annotations

import re
from typing import Optional

LEGAL_SUFFIXES = [
    "national association", "n a", "incorporated", "corporation", "company",
    "group", "holdings", "services", "worldwide", "international", "americas",
    "capital", "investment management", "investment group", "systematic strategies",
    "co", "corp", "inc", "llc", "llp", "ltd", "plc", "sa", "nv", "se",
]

_PUNCT_RE = re.compile(r"[^a-z0-9\s]")
_WS_RE = re.compile(r"\s+")

# posting-board company name -> DOL employer name fragment to search for.
# Keys are matched case-insensitively against postings.json "company" values
# (after normalize_name). Only needed where normalization alone would miss
# the match, or where the name is short enough to trip the length guard.
ALIASES = {
    "jpmorganchase": "jpmorgan chase",
    "de shaw": "d e shaw",
    "d e shaw": "d e shaw",
    "dtcc": "depository trust",
    "imc": "imc financial markets",
    "imc trading": "imc financial markets",
    "tower research": "tower research capital",
    "tower research capital": "tower research capital",
    "susquehanna": "susquehanna international",
    "susquehanna investment group": "susquehanna international",
    "citi": "citibank",
    "bofa": "bank of america",
    "jump trading": "jump trading",
    "jump trading group": "jump trading",
    "two sigma": "two sigma",
    "point72": "point72",
    "optiver": "optiver",
    "citadel": "citadel",
    "cubist systematic strategies": "cubist systematic strategies",
    "aquatic": "aquatic capital",
    "aquatic capital": "aquatic capital",
    "naive": "naive",
    "naïve": "naive",
    "gd mission systems": "general dynamics mission systems",
    "general dynamics mission systems, inc.": "general dynamics mission systems",
    "solar turbines (caterpillar)": "solar turbines",
    "intercontinental exchange, inc.": "intercontinental exchange",
    "sk hynix memory solution": "sk hynix",
}

# Companies deliberately never matched via substring even if long enough -
# generic English words that happen to be company names on the tracker board
# and would otherwise pick up unrelated DOL filings.
SUBSTRING_BLOCKLIST = {"neo", "nash", "asm", "abundant", "podium", "homebase", "org"}

MIN_SUBSTRING_LEN = 6


def normalize_name(name: str) -> str:
    name = name.lower()
    name = name.replace("&", " and ")
    name = _PUNCT_RE.sub(" ", name)
    tokens = [t for t in _WS_RE.split(name) if t]
    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def alias_target(posting_company: str) -> Optional[str]:
    key = normalize_name(posting_company)
    return ALIASES.get(key)


def names_match(posting_company: str, dol_employer_name: str) -> bool:
    posting_norm = normalize_name(posting_company)
    if not posting_norm:
        return False

    alias = alias_target(posting_company)
    if alias:
        return alias in normalize_name(dol_employer_name)

    if posting_norm in SUBSTRING_BLOCKLIST:
        return False
    if len(posting_norm) < MIN_SUBSTRING_LEN:
        return False

    employer_norm = normalize_name(dol_employer_name)
    return posting_norm in employer_norm or employer_norm in posting_norm
