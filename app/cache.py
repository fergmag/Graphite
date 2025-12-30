import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

CACHE_DIR = "cache"


def _safe_key(query: str) -> str:
    h = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
    return h


def cache_path_for_query(query: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{_safe_key(query)}.json")


def write_cache(query: str, payload: Dict[str, Any]) -> str:
    path = cache_path_for_query(query)
    data = {
        "query": query,
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def read_cache(query: str) -> Optional[Dict[str, Any]]:
    path = cache_path_for_query(query)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
