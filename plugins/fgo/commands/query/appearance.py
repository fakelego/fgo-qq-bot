"""/形象 命令 — 输出从者的各阶段图标与战斗形象截图"""
from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment, Message
from nonebot.params import CommandArg

from ...services.query.svt_search import query_svt_detail_by_keyword_cn_first
from ...services.wiki_screenshot import capture_servant_sections

appearance_cmd = on_command("形象", aliases={"战斗形象", "立绘", "appearance", "skin"}, priority=5)


@appearance_cmd.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    keyword = arg.extract_plain_text().strip()
    if not keyword:
        await appearance_cmd.finish("用法：/形象 关键词\n例如：/形象 摩根")

    try:
        result = await query_svt_detail_by_keyword_cn_first(keyword)
    except Exception as e:
        await appearance_cmd.finish(f"查询失败（网络或数据源异常）：{type(e).__name__}: {e}")

    if not result:
        await appearance_cmd.finish(
            f"未命中从者，关键词：{keyword}\n"
            "可先在 plugins/fgo/data/aliases/servant_cn.yaml 添加别名映射"
        )

    try:
        sections = await capture_servant_sections(result.cn_name, timeout_ms=15000)
    except Exception:
        sections = []

    if not sections:
        await appearance_cmd.finish(f"{result.cn_name}\n（截图暂时不可用）")

    target = [s for s in sections if s.title.startswith("各阶段图标") or s.title.startswith("立绘")]

    if not target:
        await appearance_cmd.finish(f"{result.cn_name}\n（未找到形象信息）")

    await appearance_cmd.finish(MessageSegment.image(target[0].png_bytes))
