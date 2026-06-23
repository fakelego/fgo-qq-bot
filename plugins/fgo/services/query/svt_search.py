from __future__ import annotations

from dataclasses import dataclass

from typing import Any
from ...stores.atlas_client import get_servant_detail_cn_with_jp_growth_fallback

from ...stores.aliases_servant_cn import find_servant_alias
from ...stores.atlas_client import get_servant_basic_by_id, AtlasServantBrief


@dataclass(frozen=True)
class SvtResult:
    atlas: AtlasServantBrief
    cn_name: str | None = None
    mooncell_url: str | None = None


def mooncell_servant_url(cn_name: str) -> str:
    # 简单用搜索入口，稳定不依赖具体页面名
    # 也可以换成直达页面，但直达依赖页面命名规范
    # fgo.wiki 的搜索参数可能会变化，但通常比模板爬虫稳定
    from urllib.parse import quote
    return f"https://fgo.wiki/index.php?search={quote(cn_name)}"


async def query_svt_by_keyword_cn_first(keyword: str) -> SvtResult | None:
    """
    CN 优先体验：先走本地别名表 -> atlas id -> Atlas API
    """
    hit = find_servant_alias(keyword)
    if not hit:
        return None

    atlas = await get_servant_basic_by_id(hit.atlas_id)
    cn_name = hit.display_name or keyword
    return SvtResult(
        atlas=atlas,
        cn_name=cn_name,
        mooncell_url=mooncell_servant_url(cn_name),
    )

@dataclass(frozen=True)
class SvtDetailResult:
    atlas_id: int
    cn_name: str
    mooncell_url: str | None
    detail: dict[str, Any]


async def query_svt_detail_by_keyword_cn_first(keyword: str) -> SvtDetailResult | None:
    hit = find_servant_alias(keyword)
    if not hit:
        return None

    detail = await get_servant_detail_cn_with_jp_growth_fallback(hit.atlas_id)
    cn_name = hit.display_name or str(detail.get("name") or keyword)

    return SvtDetailResult(
        atlas_id=hit.atlas_id,
        cn_name=cn_name,
        mooncell_url=mooncell_servant_url(cn_name),
        detail=detail,
    )