from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class PriceSummary:
    n: int
    median: Optional[float]
    trimmed_mean: Optional[float]
    p25: Optional[float]
    p75: Optional[float]
    min_price: Optional[float]
    max_price: Optional[float]
    confidence: float


def _median(xs: List[float]) -> float:
    xs = sorted(xs)
    n = len(xs)
    mid = n // 2
    if n % 2 == 1:
        return xs[mid]
    return (xs[mid - 1] + xs[mid]) / 2.0


def _percentile(xs: List[float], p: float) -> float:
    xs = sorted(xs)
    if not xs:
        raise ValueError("empty list")
    if p <= 0:
        return xs[0]
    if p >= 100:
        return xs[-1]

    k = (len(xs) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    if f == c:
        return xs[f]
    d0 = xs[f] * (c - k)
    d1 = xs[c] * (k - f)
    return d0 + d1


def _trimmed_mean(xs: List[float], trim_frac: float = 0.1) -> float:
    xs = sorted(xs)
    n = len(xs)
    k = int(n * trim_frac)
    core = xs[k : n - k] if n - 2 * k > 0 else xs
    return sum(core) / len(core)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def summarize_prices(prices: List[float]) -> PriceSummary:
    clean = [float(p) for p in prices if p is not None]
    clean = [p for p in clean if p > 0]

    n = len(clean)
    if n == 0:
        return PriceSummary(
            n=0,
            median=None,
            trimmed_mean=None,
            p25=None,
            p75=None,
            min_price=None,
            max_price=None,
            confidence=0.0,
        )

    med = _median(clean)
    p25 = _percentile(clean, 25)
    p75 = _percentile(clean, 75)
    tmean = _trimmed_mean(clean, trim_frac=0.1) if n >= 5 else sum(clean) / n

    min_p = min(clean)
    max_p = max(clean)

    size_score = 1.0 - (1.0 / (1.0 + n / 8.0))  

    iqr = max(p75 - p25, 0.0)
    rel_spread = iqr / med if med > 0 else 1.0
    spread_score = 1.0 - _clamp(rel_spread, 0.0, 1.0)

    confidence = _clamp(0.65 * size_score + 0.35 * spread_score, 0.0, 1.0)

    return PriceSummary(
        n=n,
        median=round(med, 2),
        trimmed_mean=round(tmean, 2),
        p25=round(p25, 2),
        p75=round(p75, 2),
        min_price=round(min_p, 2),
        max_price=round(max_p, 2),
        confidence=round(confidence, 3),
    )


def comps_to_prices(comps: List[Dict[str, Any]], include_shipping: bool = False) -> List[float]:
    prices: List[float] = []
    for c in comps:
        p = c.get("price")
        if p is None:
            continue
        total = float(p)
        if include_shipping:
            s = c.get("shipping")
            if s is not None:
                total += float(s)
        prices.append(total)
    return prices


def to_dict(summary: PriceSummary) -> Dict[str, Any]:
    return asdict(summary)
