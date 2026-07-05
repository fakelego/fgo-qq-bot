"""/资料 命令 — /资料 输出角色详情；/资料1~/资料6 输出个人资料1~6"""
from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment, Message
from nonebot.params import CommandArg

from ...services.query.svt_search import query_svt_detail_by_keyword_cn_first
from ...services.wiki_screenshot import capture_servant_sections


async def _get_sections(keyword: str):
    """通用：查从者 → 截图 → 返回 sections 列表和 cn_name"""
    from nonebot import get_bot

    result = await query_svt_detail_by_keyword_cn_first(keyword)
    if not result:
        return None, None

    try:
        sections = await capture_servant_sections(result.cn_name, timeout_ms=15000)
    except Exception:
        sections = []

    return result.cn_name, sections


# ── /资料 → 角色详情 ──────────────────────────────────────
profile_cmd = on_command("资料", aliases={"profile"}, priority=5)


@profile_cmd.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    keyword = arg.extract_plain_text().strip()
    if not keyword:
        await profile_cmd.finish("用法：/资料 关键词\n例如：/资料 摩根")

    cn_name, sections = await _get_sections(keyword)
    if cn_name is None:
        await profile_cmd.finish(
            f"未命中从者，关键词：{keyword}\n"
            "可先在 plugins/fgo/data/aliases/servant_cn.yaml 添加别名映射"
        )
    if not sections:
        await profile_cmd.finish(f"{cn_name}\n（截图暂时不可用）")

    target = [s for s in sections if s.title == "资料(角色详情)"]
    if not target:
        await profile_cmd.finish(f"{cn_name}\n（未找到角色详情）")

    await profile_cmd.finish(MessageSegment.image(target[0].png_bytes))


# ── /资料1 ~ /资料6 → 个人资料1~6 ───────────────────────────

def _make_profile_handler(n: int):
    """生成第 n 个个人资料的 handler（n=1~6）"""

    async def handler(event: MessageEvent, arg: Message = CommandArg()):
        keyword = arg.extract_plain_text().strip()
        if not keyword:
            await handler._matcher.finish(f"用法：/资料{n} 关键词")

        cn_name, sections = await _get_sections(keyword)
        if cn_name is None:
            await handler._matcher.finish(
                f"未命中从者，关键词：{keyword}\n"
                "可先在 plugins/fgo/data/aliases/servant_cn.yaml 添加别名映射"
            )
        if not sections:
            await handler._matcher.finish(f"{cn_name}\n（截图暂时不可用）")

        label = f"资料(个人资料{n})"
        target = [s for s in sections if s.title == label]
        if not target:
            await handler._matcher.finish(f"{cn_name}\n（未找到「{label}」）")

        await handler._matcher.finish(MessageSegment.image(target[0].png_bytes))

    return handler


# 注册 /资料1 ~ /资料6 各自的 matcher
_profile_matchers: dict[int, object] = {}

for _n in range(1, 7):
    _cmd = on_command(f"资料{_n}", priority=5)
    _h = _make_profile_handler(_n)
    # 把 matcher 引用挂到 handler 上，供 finish 使用
    _h._matcher = _cmd
    _cmd.handle()(_h)
    _profile_matchers[_n] = _cmd
