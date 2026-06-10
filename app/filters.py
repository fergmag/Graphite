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

# Map Carhartt colorway names to their common search term.
# Keep this conservative — only map when the two terms are genuinely interchangeable.
_COLOR_SYNONYMS = {
    "crimson":       "red",
    "hunter green":  "green",
    "moss":          "green",
    "sage":          "green",
    "forest green":  "green",
    "duck brown":    "brown",
    "carhartt brown":"brown",
    "dark brown":    "brown",
    "deep blue":     "navy",
    "dark navy":     "navy",
    "midnight blue": "navy",
}


def normalize_query(query: str) -> str:
    """
    Lowercase + replace size words and color synonyms so that
    'J01 Medium' and 'J01 M', or 'J01 Crimson' and 'J01 Red',
    resolve to the same cache key and eBay query.
    """
    q = query.strip().lower()

    # Colors first (multi-word phrases before single-word sizes)
    for phrase, canonical in _COLOR_SYNONYMS.items():
        q = q.replace(phrase, canonical)

    # Sizes: only replace whole words
    for word, canonical in _SIZE_SYNONYMS.items():
        q = re.sub(rf"\b{re.escape(word)}\b", canonical, q)

    # Collapse any double spaces
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
