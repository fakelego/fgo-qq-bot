"""素材/道具别名查找 — 加载 material_cn.yaml，支持关键词匹配"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

ALIASES_PATH = Path(__file__).parent.parent / "data" / "aliases" / "material_cn.yaml"


@dataclass(frozen=True)
class MaterialHit:
    name: str
    category: str
    name_jp: str | None = None
    name_en: str | None = None


_alias_map: dict[str, dict] | None = None


def _norm(s: str) -> str:
    return s.strip().lower()


def load_alias_map() -> dict[str, dict]:
    """加载素材别名表。

    YAML 格式:
        items:
          "英雄之证":
            category: 铜素材
            name_jp: 英雄の証
            name_en: Proof of Hero
            aliases: ["英雄之证", "英雄の証", "Proof of Hero"]
    """
    global _alias_map
    if _alias_map is not None:
        return _alias_map

    if not ALIASES_PATH.exists():
        _alias_map = {}
        return _alias_map

    data = yaml.safe_load(ALIASES_PATH.read_text(encoding="utf-8")) or {}
    items = data.get("items", {})
    out: dict[str, dict] = {}

    if isinstance(items, dict):
        for display_name, info in items.items():
            if not isinstance(info, dict):
                continue

            aliases = info.get("aliases") or []
            keys = [str(display_name)] + [str(a) for a in aliases] if isinstance(aliases, list) else [str(display_name)]
            for k in keys:
                nk = _norm(k)
                if not nk:
                    continue
                out[nk] = {
                    "name": str(display_name),
                    "category": str(info.get("category") or ""),
                    "name_jp": str(info.get("name_jp") or ""),
                    "name_en": str(info.get("name_en") or ""),
                }
    _alias_map = out
    return out


def find_material(keyword: str) -> Optional[MaterialHit]:
    """按关键词查找素材。先精确匹配，再包含匹配。"""
    amap = load_alias_map()
    nk = _norm(keyword)
    if not nk:
        return None

    # 精确匹配
    if nk in amap:
        v = amap[nk]
        return MaterialHit(
            name=v["name"],
            category=v["category"],
            name_jp=v.get("name_jp"),
            name_en=v.get("name_en"),
        )

    # 包含匹配
    for k, v in amap.items():
        if nk in k:
            return MaterialHit(
                name=v["name"],
                category=v["category"],
                name_jp=v.get("name_jp"),
                name_en=v.get("name_en"),
            )

    return None
