from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional


DEFAULT_PROFILES_PATH = os.path.join("app", "models.json")


@dataclass
class ModelProfile:
    key: str
    casp: Optional[float] = None
    accuracy_pct: Optional[int] = None  # 0..100 step 10
    note: Optional[str] = None


def _quantize_10(x: int) -> int:
    q = int(round(x / 10.0) * 10)
    return max(0, min(100, q))


def load_profiles(path: str = DEFAULT_PROFILES_PATH) -> Dict[str, ModelProfile]:
    if not os.path.exists(path):
        return {}

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    profiles: Dict[str, ModelProfile] = {}
    for k, v in (raw or {}).items():
        if not isinstance(v, dict):
            continue

        casp = v.get("casp")
        acc = v.get("accuracy_pct")
        note = v.get("note")

        try:
            casp_f = float(casp) if casp is not None else None
        except (TypeError, ValueError):
            casp_f = None

        try:
            acc_i = int(acc) if acc is not None else None
        except (TypeError, ValueError):
            acc_i = None

        if acc_i is not None:
            acc_i = _quantize_10(acc_i)

        profiles[str(k).strip().lower()] = ModelProfile(
            key=str(k).strip(),
            casp=casp_f,
            accuracy_pct=acc_i,
            note=str(note) if note is not None else None,
        )

    return profiles


def match_profile(query: str, profiles: Dict[str, ModelProfile]) -> Optional[ModelProfile]:
    """
    Simple match:
    - exact key match (case-insensitive) wins
    - otherwise, substring match on the key (first hit) as a convenience
    """
    q = (query or "").strip().lower()
    if not q:
        return None

    if q in profiles:
        return profiles[q]

    # substring match
    for key_lc, prof in profiles.items():
        if key_lc and key_lc in q:
            return prof

    return None


def apply_profile_to_public(public_obj: Dict[str, Any], profile: ModelProfile) -> Dict[str, Any]:
    """
    Override CASP/accuracy if provided in the profile.
    """
    out = dict(public_obj)

    if profile.casp is not None:
        out["casp"] = round(float(profile.casp), 2)

    if profile.accuracy_pct is not None:
        out["accuracy_pct"] = int(profile.accuracy_pct)

        # label can remain whatever public_view computed; but we can refresh it lightly
        pct = out["accuracy_pct"]
        if pct >= 80:
            out["accuracy_label"] = "Very High"
        elif pct >= 60:
            out["accuracy_label"] = "High"
        elif pct >= 40:
            out["accuracy_label"] = "Medium"
        elif pct >= 20:
            out["accuracy_label"] = "Low"
        else:
            out["accuracy_label"] = "Very Low"

    if profile.note:
        out["profile_note"] = profile.note

    return out
