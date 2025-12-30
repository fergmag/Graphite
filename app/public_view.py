from typing import Any, Dict, Optional


def confidence_label(confidence_0_to_1: float) -> str:
    if confidence_0_to_1 >= 0.75:
        return "High"
    if confidence_0_to_1 >= 0.45:
        return "Medium"
    return "Low"


def deal_score_and_label(estimate: float, asking: float) -> Dict[str, Any]:
    """
    Maps asking vs estimate into a 1–5 deal score.

    Discount ratio = (estimate - asking) / estimate

    5: 25%+ under
    4: 15–25% under
    3: within +/- 15%
    2: 15–25% over
    1: 25%+ over
    """
    if estimate <= 0:
        return {"deal_score": None, "deal_label": None, "delta": None, "delta_pct": None}

    delta = estimate - asking
    delta_pct = delta / estimate 
    if delta_pct >= 0.25:
        score, label = 5, "Steal"
    elif delta_pct >= 0.15:
        score, label = 4, "Good"
    elif delta_pct >= -0.15:
        score, label = 3, "Fair"
    elif delta_pct >= -0.25:
        score, label = 2, "Bad"
    else:
        score, label = 1, "Overpriced"

    return {
        "deal_score": score,
        "deal_label": label,
        "delta": round(delta, 2),
        "delta_pct": round(delta_pct * 100, 1),  # percent
    }


def build_public(summary: Dict[str, Any], asking: Optional[float] = None) -> Dict[str, Any]:
    estimate = summary.get("median") or summary.get("trimmed_mean")
    confidence = float(summary.get("confidence") or 0.0)

    public = {
        "estimate": estimate,
        "confidence_pct": int(round(confidence * 100)),
        "confidence_label": confidence_label(confidence),
    }

    if asking is not None and estimate is not None:
        public.update(deal_score_and_label(float(estimate), float(asking)))

    return public
