from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Optional

import aiohttp


ATLAS_BASE = "https://api.atlasacademy.io"


class AtlasAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class AtlasServantBrief:
    id: int
    name: str
    className: str
    rarity: int
    collectionNo: int | None = None


_session: aiohttp.ClientSession | None = None
_session_lock = asyncio.Lock()

# 简单缓存：id -> detail json
_servant_cache: dict[tuple[str, int], dict[str, Any]] = {}


async def _get_session() -> aiohttp.ClientSession:
    global _session
    async with _session_lock:
        if _session is None or _session.closed:
            _session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12))
        return _session


async def atlas_get_json(path: str) -> Any:
    url = f"{ATLAS_BASE}{path}"
    sess = await _get_session()
    async with sess.get(url) as resp:
        if resp.status != 200:
            text = await resp.text()
            raise AtlasAPIError(f"Atlas API {resp.status}: {text[:200]}")
        return await resp.json()


async def get_servant_basic_by_id(svt_id: int) -> AtlasServantBrief:
    # Atlas 的 nice servant detail 很大，但字段全；这里直接拿 detail 再抽字段。
    if svt_id in _servant_cache:
        data = _servant_cache[svt_id]
    else:
        data = await atlas_get_json(f"/nice/JP/servant/{svt_id}")
        if isinstance(data, dict):
            _servant_cache[svt_id] = data
        else:
            raise AtlasAPIError("Unexpected servant payload")

    name = str(data.get("name") or "")
    className = str(data.get("className") or "")
    rarity = int(data.get("rarity") or 0)
    collectionNo = data.get("collectionNo")
    try:
        collectionNo = int(collectionNo) if collectionNo is not None else None
    except Exception:
        collectionNo = None

    return AtlasServantBrief(
        id=svt_id,
        name=name,
        className=className,
        rarity=rarity,
        collectionNo=collectionNo,
    )

def _norm_region(region: str) -> str:
    r = (region or "JP").upper()
    if r not in ("JP", "CN", "TW", "NA", "KR"):
        r = "JP"
    return r


async def get_servant_detail(region: str, svt_id: int) -> dict[str, Any]:
    """
    取 servant detail（nice）完整 JSON。
    """
    region = _norm_region(region)
    key = (region, int(svt_id))
    if key in _servant_cache:
        return _servant_cache[key]

    data = await atlas_get_json(f"/nice/{region}/servant/{svt_id}")
    if not isinstance(data, dict):
        raise AtlasAPIError("Unexpected servant payload")

    _servant_cache[key] = data
    return data


def _need_growth_to_120(detail: dict[str, Any]) -> bool:
    atk = detail.get("atkGrowth") or []
    hp = detail.get("hpGrowth") or []
    return not (isinstance(atk, list) and isinstance(hp, list) and len(atk) >= 120 and len(hp) >= 120)


async def get_servant_detail_cn_with_jp_growth_fallback(svt_id: int) -> dict[str, Any]:
    """
    CN 为主（中文名、资源、字段），但如果 CN 的 growth 不足 120，则用 JP 的 growth 补齐。
    """
    cn = await get_servant_detail("CN", svt_id)
    if not _need_growth_to_120(cn):
        return cn

    jp = await get_servant_detail("JP", svt_id)

    # 只补数值相关，避免覆盖 CN 的文本/资源
    if isinstance(jp.get("atkGrowth"), list) and len(jp["atkGrowth"]) > len(cn.get("atkGrowth") or []):
        cn["atkGrowth"] = jp["atkGrowth"]
    if isinstance(jp.get("hpGrowth"), list) and len(jp["hpGrowth"]) > len(cn.get("hpGrowth") or []):
        cn["hpGrowth"] = jp["hpGrowth"]

    # 有些字段 CN 可能缺失，做兜底
    for k in ("atkBase", "atkMax", "hpBase", "hpMax", "lvMax"):
        if cn.get(k) is None and jp.get(k) is not None:
            cn[k] = jp[k]

    return cn