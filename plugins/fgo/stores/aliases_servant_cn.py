from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml  # PyYAML


ALIASES_PATH = Path(__file__).parent.parent / "data" / "aliases" / "servant_cn.yaml"


@dataclass(frozen=True)
class AliasHit:
    atlas_id: int
    key: str  # 命中的 alias key
    display_name: str | None = None  # 可选：用于展示的中文名


_alias_map: dict[str, dict] | None = None


def _norm(s: str) -> str:
    return s.strip().lower()


def load_alias_map() -> dict[str, dict]:
    """
    文件格式建议（见下方示例）：
    servants:
      "摩根":
        atlas_id: 302
        aliases: ["妖精骑士女王", "morgan"]
      "奥伯龙":
        atlas_id: 321
        aliases: ["obéron", "oberon", "虫王"]
    """
    global _alias_map
    if _alias_map is not None:
        return _alias_map

    if not ALIASES_PATH.exists():
        _alias_map = {}
        return _alias_map

    data = yaml.safe_load(ALIASES_PATH.read_text(encoding="utf-8")) or {}
    servants = data.get("servants", {})
    out: dict[str, dict] = {}

    if isinstance(servants, dict):
        for display_name, info in servants.items():
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


def find_servant_alias(keyword: str) -> Optional[AliasHit]:
    amap = load_alias_map()
    nk = _norm(keyword)
    if not nk:
        return None

    # 先精确匹配
    if nk in amap:
        v = amap[nk]
        return AliasHit(atlas_id=int(v["atlas_id"]), key=nk, display_name=v.get("display_name"))

    # 再做包含匹配（避免太“智能”，先简单）
    # 例如 keyword="妖精骑士" 命中 "妖精骑士女王"
    for k, v in amap.items():
        if nk in k:
            return AliasHit(atlas_id=int(v["atlas_id"]), key=k, display_name=v.get("display_name"))

    return None