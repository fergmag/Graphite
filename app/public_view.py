from __future__ import annotations

from typing import Any, Dict, Optional


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def quantize_to_10(pct: float) -> int:
    """
    Round a percent value to the nearest 10: 0, 10, 20, ... 100
    """
    q = int(round(pct / 10.0) * 10)
    return max(0, min(100, q))


def accuracy_pct_from_confidence(confidence_0_to_1: float, n: int) -> int:
    """
    Convert internal confidence (0..1) into a user-facing Accuracy % in steps of 10.

    Rules:
    - If n == 0 -> 0%
    - Otherwise -> at least 10% (because we have *some* comps)
    """
    if n <= 0:
        return 0

    raw = _clamp(float(confidence_0_to_1), 0.0, 1.0) * 100.0
    q = quantize_to_10(raw)

    # Avoid showing 0% when we actually have comps
    return max(10, q)


def accuracy_label(pct: int) -> str:
    """
    Short label for UI only.
    """
    if pct >= 80:
        return "Very High"
    if pct >= 60:
        return "High"
    if pct >= 40:
        return "Medium"
    if pct >= 20:
        return "Low"
    return "Very Low"


def deal_score(casp: float, asking: float) -> Dict[str, Any]:
    """
    Returns a simple 1–5 deal score.
    - 5 = amazing deal (asking much lower than CASP)
    - 3 = fair
    - 1 = terrible deal (asking much higher than CASP)
    """
    if casp <= 0 or asking <= 0:
        return {}

    delta = casp - asking
    delta_pct = (delta / casp) * 100.0

    # You can tune these thresholds later
    if delta_pct >= 25:
        score, label = 5, "Great"
    elif delta_pct >= 15:
        score, label = 4, "Good"
    elif delta_pct >= -10:
        score, label = 3, "Fair"
    elif delta_pct >= -25:
        score, label = 2, "Bad"
    else:
        score, label = 1, "Terrible"

    return {
        "deal_score": score,
        "deal_label": label,
        "delta": round(delta, 2),
        "delta_pct": round(delta_pct, 1),
        "asking": round(float(asking), 2),
    }


def build_public_response(summary: Dict[str, Any], asking: Optional[float] = None) -> Dict[str, Any]:
    """
    Converts the internal summary (from pricing.py / to_dict()) into a clean, user-facing object.

    CASP choice:
    - For now CASP = median (stable + robust).
    - Later we can switch to trimmed_mean or ML.
    """
    n = int(summary.get("n") or 0)

    # CASP = median (fallback to trimmed_mean if median missing)
    median = summary.get("median")
    trimmed_mean = summary.get("trimmed_mean")

    casp_val: Optional[float] = None
    if median is not None:
        casp_val = float(median)
    elif trimmed_mean is not None:
        casp_val = float(trimmed_mean)

    confidence = float(summary.get("confidence") or 0.0)
    acc_pct = accuracy_pct_from_confidence(confidence, n)

    public: Dict[str, Any] = {
        "casp": round(casp_val, 2) if casp_val is not None else None,
        "casp_label": "Calculated average sold price",
        "accuracy_pct": acc_pct,
        "accuracy_label": accuracy_label(acc_pct),
    }

    if asking is not None and casp_val is not None:
        public.update(deal_score(casp_val, asking))

    return public
