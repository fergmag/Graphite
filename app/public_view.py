from typing import Any, Dict, Optional


def quantize_pct(confidence_0_to_1: float) -> int:
    """
    Quantize confidence to 0,10,20..100.
    """
    try:
        x = float(confidence_0_to_1)
    except Exception:
        x = 0.0
    x = max(0.0, min(1.0, x))
    pct = int(round(x * 100 / 10) * 10)
    return max(0, min(100, pct))


def accuracy_label(pct: int) -> str:
    if pct >= 70:
        return "High"
    if pct >= 40:
        return "Medium"
    return "Low"


def deal_score(casp: float, asking: Optional[float]) -> Dict[str, Any]:
    """
    Returns a 1–5 deal score based on how far below CASP the asking price is.
    """
    if asking is None:
        return {
            "deal_score": None,
            "deal_label": None,
            "delta": None,
            "delta_pct": None,
        }
    if casp <= 0:
        return {
            "deal_score": None,
            "deal_label": None,
            "delta": None,
            "delta_pct": None,
        }

    a = float(asking)
    delta = float(casp) - a
    delta_pct = (delta / float(casp)) * 100.0

    # thresholds are relative to CASP
    # (more below CASP => better deal)
    if delta_pct >= 25:
        score, label = 5, "Steal"
    elif delta_pct >= 15:
        score, label = 4, "Great"
    elif delta_pct >= 7:
        score, label = 3, "Good"
    elif delta_pct >= -5:
        score, label = 2, "Fair"
    else:
        score, label = 1, "Overpriced"

    return {
        "deal_score": score,
        "deal_label": label,
        "delta": round(delta, 2),
        "delta_pct": round(delta_pct, 1),
    }


def build_public_payload(
    *,
    casp: Optional[float],
    confidence: float,
    asking: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Minimal user-facing payload. CASP = Calculated Average Sold Price.
    """
    casp_val = None if casp is None else float(casp)

    pct = quantize_pct(confidence)
    public: Dict[str, Any] = {
        "casp": None if casp_val is None else round(casp_val, 2),
        "accuracy_pct": pct,
        "accuracy_label": accuracy_label(pct),
        # keep raw confidence for DB/debugging only
        "confidence_raw": round(float(confidence), 3),
    }

    if casp_val is not None and asking is not None:
        public.update(deal_score(casp_val, asking))
    else:
        public.update(
            {"deal_score": None, "deal_label": None, "delta": None, "delta_pct": None}
        )

    return public
