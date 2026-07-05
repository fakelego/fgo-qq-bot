"""礼装别名查找 — 加载 equip_cn.yaml，支持关键词匹配"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

ALIASES_PATH = Path(__file__).parent.parent / "data" / "aliases" / "equip_cn.yaml"


@dataclass(frozen=True)
class EquipAliasHit:
    atlas_id: int
    key: str
    display_name: str | None = None


_alias_map: dict[str, dict] | None = None


def _norm(s: str) -> str:
    return s.strip().lower()


def load_alias_map() -> dict[str, dict]:
    global _alias_map
    if _alias_map is not None:
        return _alias_map

    if not ALIASES_PATH.exists():
        _alias_map = {}
        return _alias_map

    data = yaml.safe_load(ALIASES_PATH.read_text(encoding="utf-8")) or {}
    equips = data.get("equips", {})
    out: dict[str, dict] = {}

    if isinstance(equips, dict):
        for display_name, info in equips.items():
            if not isinstance(info, dict):
                continue
            atlas_id = info.get("atlas_id")
            try:
                atlas_id = int(atlas_id)
            except Exception:
                continue

            aliases = info.get("aliases") or []
            keys = [str(display_name)] + [str(a) for a in aliases] if isinstance(aliases, list) else [str(display_name)]
            for k in keys:
                nk = _norm(k)
                if not nk:
                    continue
                out[nk] = {"atlas_id": atlas_id, "display_name": str(display_name)}

    _alias_map = out
    return out


def find_equip_alias(keyword: str) -> Optional[EquipAliasHit]:
    amap = load_alias_map()
    nk = _norm(keyword)
    if not nk:
        return None

    # 精确匹配
    if nk in amap:
        v = amap[nk]
        return EquipAliasHit(atlas_id=int(v["atlas_id"]), key=nk, display_name=v.get("display_name"))

    # 包含匹配
    for k, v in amap.items():
        if nk in k:
            return EquipAliasHit(atlas_id=int(v["atlas_id"]), key=k, display_name=v.get("display_name"))

    return None
