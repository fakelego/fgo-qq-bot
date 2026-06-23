from __future__ import annotations
from typing import Literal

Region = Literal["cn", "jp", "tw"]




def get_default_region(user_id: str) -> Region:
    return DEFAULT_REGION_BY_USER.get(user_id, "cn")


def normalize_region(s: str) -> Region | None:
    s = s.strip().lower()
    if s in ("cn", "jp", "tw"):
        return s  # type: ignore[return-value]
    return None