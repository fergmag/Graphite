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

# Matches Carhartt jacket codes: J97, J65, JB0817, JS1237, JR0115, etc.
_NUMERIC_CODE_RE = re.compile(r"\b(J[A-Z]?\d{2,})\b", re.IGNORECASE)


def filter_comps(comps: List[Dict[str, Any]], query: str, require_code: bool = True) -> List[Dict[str, Any]]:
    """
    Drop junk listings from comps.
    - Removes titles containing known irrelevant terms (kids, women's, vest, etc.)
    - If require_code=True (default) and query has a jacket code, that code must
      appear in the title. Set require_code=False for platforms like Etsy/Depop
      where the search is targeted and sellers don't put model codes in titles.
    """
    code_match = _NUMERIC_CODE_RE.search(query)
    required_code = code_match.group(1).lower() if (code_match and require_code) else None

    filtered = []
    for comp in comps:
        title_lower = (comp.get("title") or "").lower()

        if any(term in title_lower for term in JUNK_TERMS):
            continue

        if required_code and required_code not in title_lower:
            continue

        filtered.append(comp)

    return filtered


# ── Size parsing from listing titles ─────────────────────────────────────────

_SIZE_TITLE_MAP = {
    'xxl': 'XXL', '2xl': 'XXL', 'xxlarge': 'XXL', '2xlarge': 'XXL', '2xlrg': 'XXL',
    'xlarge': 'XL', 'xl': 'XL', 'xlrg': 'XL',
    'large': 'L', 'l': 'L', 'lrg': 'L',
    'medium': 'M', 'm': 'M', 'med': 'M',
}

# Ordered from most-specific to least to avoid 'XL' matching inside 'XXL'
_XXL = r'(?:xxl|2xl|2x\s*large|2x\s*l|xx-?large)'
_XL  = r'(?:xl|x-?large)'
_L   = r'(?:large|lrg)'
_M   = r'medium'

_SIZE_TITLE_RE = re.compile(
    # "size XXL", "size: XL", "sz M" — prefixed by size/sz keyword
    rf'\b(?:size|sz)[:\s]+?({_XXL}|{_XL}|{_L}|{_M}|[ml])\b'
    # (XXL), (XL), (M), (L) — parenthesized
    rf'|\(({_XXL}|{_XL}|{_L}|{_M}|[ml])\)'
    # full words without prefix
    rf'|\b({_XXL}|{_XL}|{_L}|{_M})\b'
    # standalone M or L at a word boundary (last resort — most ambiguous)
    r'|\b([ML])\b',
    re.IGNORECASE,
)


def normalize_size(s: Optional[str]) -> Optional[str]:
    """Normalize a raw size string (e.g. 'l', 'Large', 'X-Large') to M/L/XL/XXL."""
    if not s:
        return None
    key = s.strip().lower().replace('-', '').replace(' ', '')
    return _SIZE_TITLE_MAP.get(key)


def parse_size_from_title(title: str) -> Optional[str]:
    """Extract M/L/XL/XXL from a listing title. Returns None if not found."""
    m = _SIZE_TITLE_RE.search(title or '')
    if not m:
        return None
    raw = next((g for g in m.groups() if g is not None), None)
    if not raw:
        return None
    key = raw.lower().replace('-', '').replace(' ', '').replace('\t', '')
    # "2x large" → "2xlarge", "2xl" → "2xl"
    result = _SIZE_TITLE_MAP.get(key)
    if result:
        return result
    # Try stripping trailing 'l' for "2xlarge" → try "2xl" etc
    if key.startswith('2x'):
        return _SIZE_TITLE_MAP.get('2xl') or _SIZE_TITLE_MAP.get('xxl')
    if key.startswith('xx'):
        return _SIZE_TITLE_MAP.get('xxl')
    return None
