"""
vision.py — Claude Vision condition grading for jacket listings.

Requires ANTHROPIC_API_KEY env var. Uses claude-haiku (fast + cheap).
If the key is not set, all calls return None gracefully.
"""

import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    try:
        import anthropic
        _client = anthropic.Anthropic(api_key=api_key)
    except ImportError:
        log.warning("[vision] anthropic package not installed — pip install anthropic")
    return _client


def grade_condition(photo_url: str) -> Optional[dict]:
    """
    Grade the visible condition of a jacket from a photo URL.
    Returns {"grade": "7/10", "notes": "Light fading on shoulders, clean overall"}
    or None if grading is unavailable.
    """
    client = _get_client()
    if not client:
        return None
    if not photo_url or not (photo_url.startswith("http://") or photo_url.startswith("https://")):
        return None
    try:
        import anthropic
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=150,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "url", "url": photo_url},
                        },
                        {
                            "type": "text",
                            "text": (
                                "You are grading a vintage Carhartt jacket for a resale buyer. "
                                "Look carefully at the actual fabric, stitching, colour, and any visible damage.\n\n"
                                "Scale (be strict — sellers always photograph in flattering light):\n"
                                "9-10 = deadstock/unworn or near-mint with zero visible wear\n"
                                "8 = excellent: only very faint fading, no marks or damage\n"
                                "7 = good: noticeable fading or minor marks, no repairs needed\n"
                                "6 = fair: clear wear, staining or small repairs visible\n"
                                "5 = well-worn: significant fading, staining, fraying or multiple flaws\n"
                                "4 = heavy wear: major repairs, holes, or prominent damage\n"
                                "1-3 = damaged/wearable only for parts\n\n"
                                "Describe specifically what you see (collar wear, cuffs, fading pattern, stains, etc). "
                                "Reply in exactly this format with no extra text:\n"
                                "GRADE: X/10\n"
                                "NOTES: [one sentence describing the specific condition details you can see]"
                            ),
                        },
                    ],
                }
            ],
        )
        text = message.content[0].text.strip()
        grade = None
        notes = None
        for line in text.split("\n"):
            if line.startswith("GRADE:"):
                grade = line.replace("GRADE:", "").strip()
            elif line.startswith("NOTES:"):
                notes = line.replace("NOTES:", "").strip()
        if grade:
            return {"grade": grade, "notes": notes or ""}
    except Exception as e:
        log.error("[vision] grading failed — model=claude-sonnet-4-6 url=%s error=%s: %s",
                  photo_url[:80], type(e).__name__, e)
    return None
