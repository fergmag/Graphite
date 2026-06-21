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
            model="claude-haiku-4-5-20251001",
            max_tokens=120,
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
                                "This is a photo of a vintage Carhartt jacket listed for sale. "
                                "Grade its visible condition from 1-10 "
                                "(10=mint/unworn, 7=good used, 4=heavy wear, 1=damaged). "
                                "Reply in exactly this format with no extra text:\n"
                                "GRADE: X/10\n"
                                "NOTES: [one brief sentence on key condition details]"
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
        log.warning("[vision] grading failed for %s: %s", photo_url, e)
    return None
