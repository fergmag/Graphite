import re
from typing import Any, Dict, List, Optional

# ── Query normalization ───────────────────────────────────────────────────────

_SIZE_SYNONYMS = {
    "small":   "s",
    "medium":  "m",
    "large":   "l",
    "x-large": "xl",
    "xlarge":  "xl",
    "x large": "xl",
    "xx-large": "xxl",
    "xxlarge": "xxl",
    "xx large": "xxl",
}

# Generic color synonyms — only for terms that are NOT specific Carhartt colorway names.
# Do NOT add crimson, moss, hunter green etc. — those are real colorway names.
_COLOR_SYNONYMS = {
    "duck brown":    "brown",
    "dark brown":    "brown",
    "deep blue":     "navy",
    "dark navy":     "navy",
    "midnight blue": "navy",
}

# Carhartt colorway abbreviations → full name.
# Allows "j97 cri" and "j97 crimson" to resolve to the same cache key.
_CODE_ALIASES = {
    "brk": "brick",
    "blu": "blue",
    "cri": "crimson",
    "mos": "moss",
    "brg": "burgundy",
    "ptl": "petrol",
    "tmb": "timber",
    "cht": "chestnut",
    "onx": "onyx",
    "htg": "hunter green",
    "nat": "natural",
    "rdw": "redwood",
    "spc": "spruce",
    "dol": "dark olive",
    "dst": "darkstone",
}
# Reverse: canonical full name → abbreviation for search fallback.
# "dst" excluded — matches DST brand, "dusty", etc. Brk/blu are fine when
# qualified by a model code ("j65 brk"), so they're back in.
_ALIAS_TO_CODE: Dict[str, str] = {
    v: k for k, v in _CODE_ALIASES.items()
    if k not in ("dst",)
}

# Full reverse map (no exclusions) — used for colorway-term matching in titles.
_FULL_CANONICAL_TO_ABBREV: Dict[str, str] = {v: k for k, v in _CODE_ALIASES.items()}

# All known colorway terms (canonical + abbreviation) with precompiled word-boundary patterns.
# Used for the negative colorway check: reject only when a DIFFERENT colorway is explicit.
_ALL_COLORWAY_TERMS: set = set()
for _ck, _cv in _CODE_ALIASES.items():
    _ALL_COLORWAY_TERMS.add(_ck)
    _ALL_COLORWAY_TERMS.add(_cv)
_COLORWAY_RE: Dict[str, re.Pattern] = {
    t: re.compile(r'\b' + re.escape(t) + r'\b', re.IGNORECASE)
    for t in _ALL_COLORWAY_TERMS
}


def normalize_query(query: str) -> str:
    """
    Lowercase, expand Carhartt colorway abbreviations, normalize size words,
    and replace generic color synonyms. Ensures consistent cache keys regardless
    of whether the user types 'j97 cri' or 'j97 crimson', 'large' or 'l', etc.
    """
    q = query.strip().lower()

    # Multi-word phrases first
    for phrase, canonical in _COLOR_SYNONYMS.items():
        q = q.replace(phrase, canonical)

    # Carhartt code abbreviations (whole word only)
    for abbr, full in _CODE_ALIASES.items():
        q = re.sub(rf"\b{re.escape(abbr)}\b", full, q)

    # Size words (whole word only)
    for word, canonical in _SIZE_SYNONYMS.items():
        q = re.sub(rf"\b{re.escape(word)}\b", canonical, q)

    # Collapse extra spaces
    q = re.sub(r"\s{2,}", " ", q).strip()
    return q


def colorway_terms_for_query(query: str) -> List[str]:
    """Return colorway terms that must appear in a listing title for this query.

    For "j65 brick" returns ["brick", "brk"] so both canonical and abbreviated
    forms are accepted. Returns [] when the query has no colorway component.
    """
    code_match = _NUMERIC_CODE_RE.search(query)
    if not code_match:
        return []
    after_code = query[code_match.end():].strip()
    if not after_code:
        return []
    terms = [after_code]
    abbrev = _FULL_CANONICAL_TO_ABBREV.get(after_code)
    if abbrev:
        terms.append(abbrev)
    return terms


def negative_colorway_filter(title_lower: str, query: str) -> bool:
    """Return True (keep) if the listing passes the colorway check.

    Accepts listings with the correct colorway OR no colorway at all.
    Rejects ONLY when the title explicitly names a DIFFERENT known colorway.

    This prevents j65 BLU listings appearing in j65 BRK results without
    rejecting listings like 'Carhartt J110 Traditional Jacket' that simply
    omit the colorway name (which is common for eBay/Grailed sellers).
    Word-boundary matching so 'most' doesn't trigger 'mos', 'naturally' doesn't
    trigger 'nat', etc.
    """
    cw_terms = colorway_terms_for_query(query)
    if not cw_terms:
        return True
    for term in cw_terms:
        if _COLORWAY_RE[term].search(title_lower):
            return True  # correct colorway → keep
    other_cw = _ALL_COLORWAY_TERMS - set(cw_terms)
    for term in other_cw:
        if _COLORWAY_RE[term].search(title_lower):
            return False  # different colorway explicitly in title → reject
    return True  # no colorway mentioned at all → keep


def search_terms_for_query(query: str) -> List[str]:
    """Return search terms to try for a normalized query.

    Sellers often use abbreviations (j97 tmb) rather than the canonical name
    (j97 timber) that normalize_query produces. Returns [canonical, abbrev]
    so scrapers can try both and merge results.
    """
    terms = [query]
    for full, code in _ALIAS_TO_CODE.items():
        if full in query:
            terms.append(query.replace(full, code))
            break  # only one colorway per model typically
    return terms


# ── Junk filter ───────────────────────────────────────────────────────────────

# Titles containing these terms are almost certainly not what we want
JUNK_TERMS = [
    "kids", "kid's", "youth", "toddler", "baby", "infant",
    "women's", "womens", "woman's", "girls", "girl's",
    "boys", "boy's", "children", "child",
    "vest", "liner only",
    "shorts", "short pants", "bib overalls", "bibs", "dungarees",
    "pants", "jeans", "chaps", "hoodie", "sweatshirt", "tee ", "t-shirt",
    "quilted vest", "quilted jacket", "quilted coat",
    "rework", "reworked",
]

# Matches Carhartt jacket codes: J97, J65, JB0817, JS1237, JR0115, etc.
_NUMERIC_CODE_RE = re.compile(r"\b(J[A-Z]?\d{2,})\b", re.IGNORECASE)


def filter_comps(comps: List[Dict[str, Any]], query: str, require_code: bool = True) -> List[Dict[str, Any]]:
    """
    Drop junk listings from comps.
    - Removes titles containing known irrelevant terms (kids, women's, vest, etc.)
    - If require_code=True (default) and query has a jacket code, that code must
      appear in the title. Also enforces colorway (e.g. "brick"/"brk" for "j65 brick")
      so cross-colorway contamination is stopped at scan time.
    - Set require_code=False for platforms like Etsy/Depop where the search is
      targeted and sellers don't put model codes in titles.
    """
    code_match = _NUMERIC_CODE_RE.search(query)
    required_code = code_match.group(1).lower() if (code_match and require_code) else None

    filtered = []
    for comp in comps:
        title_lower = (comp.get("title") or "").lower()

        if "carhartt" not in title_lower:
            continue

        if any(term in title_lower for term in JUNK_TERMS):
            continue

        if required_code and required_code not in title_lower:
            continue

        filtered.append(comp)

    return filtered


# ── Size parsing from listing titles ─────────────────────────────────────────

# Priority-ordered regexes: search for larger sizes first so "Large 2X" → XXL not L
_RE_XXL = re.compile(r'\b(?:xxl|2\s*-?\s*x\s*l(?:arge)?|2\s*-?\s*xl|xx-?large|2\s*-?\s*x\b)', re.IGNORECASE)
_RE_XL  = re.compile(r'\b(?:xl|x-?large)\b', re.IGNORECASE)
_RE_L   = re.compile(r'\b(?:large|lrg)\b', re.IGNORECASE)
_RE_M   = re.compile(r'\b(?:medium|med)\b', re.IGNORECASE)
_RE_ML  = re.compile(r'\b([ML])\b')


def normalize_size(s: Optional[str]) -> Optional[str]:
    """Normalize a raw size string (e.g. 'l', 'Large', 'X-Large') to M/L/XL/XXL."""
    if not s:
        return None
    t = s.strip()
    if _RE_XXL.search(t): return 'XXL'
    if _RE_XL.search(t):  return 'XL'
    if _RE_L.search(t):   return 'L'
    if _RE_M.search(t):   return 'M'
    m = _RE_ML.search(t)
    return ('L' if m.group(1).upper() == 'L' else 'M') if m else None


def parse_size_from_title(title: str) -> Optional[str]:
    """Extract M/L/XL/XXL from a listing title. Checks larger sizes first so
    '2X Large' beats 'Large' even when 'Large' appears earlier in the string."""
    t = title or ''
    if _RE_XXL.search(t): return 'XXL'
    if _RE_XL.search(t):  return 'XL'
    if _RE_L.search(t):   return 'L'
    if _RE_M.search(t):   return 'M'
    m = _RE_ML.search(t)
    return ('L' if m.group(1).upper() == 'L' else 'M') if m else None
