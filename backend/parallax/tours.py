"""Matterport 3D tours from the CoStar kit (commercial-property.jsonl attachments).

CoStar stores a Matterport model ID as an attachment's videoKey with videoExternalReferenceType 36
(or 234). The public viewer https://my.matterport.com/show/?m=<key> opens without an API key.
"""
from __future__ import annotations

import json
from functools import lru_cache

from . import config

MATTERPORT_TYPES = {36, 234}


@lru_cache(maxsize=1)
def tours() -> dict[str, str]:
    """building_id (P<propertyId>) -> Matterport model key. Empty if the kit file isn't there."""
    path = config.DATA_DIR / "real" / "commercial-property.jsonl"
    out: dict[str, str] = {}
    if not path.exists():
        return out
    with open(path) as f:
        for line in f:
            o = json.loads(line)
            for a in o.get("attachments") or []:
                if a.get("videoExternalReferenceType") in MATTERPORT_TYPES and a.get("videoKey"):
                    out.setdefault(f"P{o['id']}", a["videoKey"])
                    break
    return out


def tour_url(building_id: str) -> str | None:
    key = tours().get(building_id)
    return f"https://my.matterport.com/show/?m={key}" if key else None
