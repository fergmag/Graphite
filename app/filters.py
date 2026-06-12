import re
from typing import Any, Dict, List

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


# ── Junk filter ───────────────────────────────────────────────────────────────

# Titles containing these terms are almost certainly not what we want
JUNK_TERMS = [
    "kids", "kid's", "youth", "toddler", "baby", "infant",
    "women's", "womens", "woman's", "girls", "girl's",
    "boys", "boy's", "children", "child",
    "vest", "liner only",
]

# Matches numeric jacket codes: J01, J97, J130, J183, etc.
_NUMERIC_CODE_RE = re.compile(r"\bJ(\d{2,})\b", re.IGNORECASE)


def filter_comps(comps: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    """
    Drop junk listings from comps.
    - Removes titles containing known irrelevant terms (kids, women's, vest, etc.)
    - If the query contains a numeric jacket code (e.g. J01, J130), requires that
      code to appear in the title too.
    """
    code_match = _NUMERIC_CODE_RE.search(query)
    required_code = code_match.group(0).lower() if code_match else None

    filtered = []
    for comp in comps:
        title_lower = (comp.get("title") or "").lower()

        if any(term in title_lower for term in JUNK_TERMS):
            continue

        if required_code and required_code not in title_lower:
            continue

        filtered.append(comp)

    return filtered
