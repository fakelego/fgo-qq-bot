"""从者查询-截图-筛选 公共辅助模块。

将重复的「查从者 → 截图 → 按标题筛选」流水线抽象为可复用组件，
消除 commands/query/ 下各命令文件中的样板代码。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..wiki_screenshot import capture_servant_sections, SectionImage
from .svt_search import query_svt_detail_by_keyword_cn_first


@dataclass(frozen=True)
class FetchResult:
    """从者查询+截图的统一结果容器。

    调用方只关心两种状态：
    - ``ok=True``  → ``cn_name`` / ``sections`` 有效
    - ``ok=False`` → ``error`` 可直接传给 matcher.finish()
    """

    ok: bool
    cn_name: str = ""
    sections: list[SectionImage] = field(default_factory=list)
    error: str = ""

    def filter(
        self,
        *,
        prefix: str | tuple[str, ...] | None = None,
        pattern: str | re.Pattern | None = None,
        exact: str | None = None,
    ) -> list[SectionImage]:
        """从 sections 中筛选匹配标题的项。

        至少提供一个参数。多个条件为 AND 关系（一般只用一个）。

        Args:
            prefix: 标题前缀匹配（可传多个前缀，满足任一即可）
            pattern: 正则匹配（可用 ``re.search``）
            exact: 精确匹配（``==``）
        """
        _prefixes: tuple[str, ...] = ()
        if isinstance(prefix, str):
            _prefixes = (prefix,)
        elif prefix is not None:
            _prefixes = prefix

        _pattern: re.Pattern | None = None
        if isinstance(pattern, str):
            _pattern = re.compile(pattern)
        elif pattern is not None:
            _pattern = pattern

        result: list[SectionImage] = []
        for s in self.sections:
            if _prefixes and not any(s.title.startswith(p) for p in _prefixes):
                continue
            if _pattern and not _pattern.search(s.title):
                continue
            if exact is not None and s.title != exact:
                continue
            result.append(s)
        return result


async def fetch(keyword: str, *, timeout_ms: int = 15000) -> FetchResult:
    """查询从者并截取 fgowiki 分节截图。

    封装完整流程：别名查找 → Atlas API → Playwright 截图。

    Args:
        keyword: 用户输入的关键词
        timeout_ms: 页面加载超时

    Returns:
        FetchResult — ok 时携带 cn_name 和 sections，失败时携带 error
    """
    # 1. 查从者
    try:
        detail = await query_svt_detail_by_keyword_cn_first(keyword)
    except Exception as e:
        return FetchResult(
            ok=False,
            error=f"查询失败（网络或数据源异常）：{type(e).__name__}: {e}",
        )

    if not detail:
        return FetchResult(
            ok=False,
            error=(
                "未命中从者（当前使用：本地国服别名表 → Atlas 结构化数据）\n"
                f"关键词：{keyword}\n"
                "你可以先在 aliases 文件里加一条映射：\n"
                "plugins/fgo/data/aliases/servant_cn.yaml\n"
            ),
        )

    # 2. 截图
    try:
        sections = await capture_servant_sections(detail.cn_name, timeout_ms=timeout_ms)
    except Exception:
        sections = []

    if not sections:
        return FetchResult(
            ok=False,
            error=f"{detail.cn_name}\n（截图暂时不可用，请点击链接查看页面）",
        )

    return FetchResult(ok=True, cn_name=detail.cn_name, sections=sections)
