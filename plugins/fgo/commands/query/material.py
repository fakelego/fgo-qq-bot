"""/素材 命令 — 输出从者的灵基再临 / 技能强化素材需求截图"""
from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment, Message
from nonebot.params import CommandArg

from ...services.query.svt_search import query_svt_detail_by_keyword_cn_first
from ...services.wiki_screenshot import capture_servant_sections

material_cmd = on_command("素材", aliases={"材料", "素材需求", "material", "mat"}, priority=5)


@material_cmd.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    keyword = arg.extract_plain_text().strip()
    if not keyword:
        await material_cmd.finish("用法：/素材 关键词\n例如：/素材 摩根")

    try:
        result = await query_svt_detail_by_keyword_cn_first(keyword)
    except Exception as e:
        await material_cmd.finish(f"查询失败（网络或数据源异常）：{type(e).__name__}: {e}")

    if not result:
        await material_cmd.finish(
            f"未命中从者，关键词：{keyword}\n"
            "可先在 plugins/fgo/data/aliases/servant_cn.yaml 添加别名映射"
        )

    try:
        sections = await capture_servant_sections(result.cn_name, timeout_ms=15000)
    except Exception:
        sections = []

    if not sections:
        await material_cmd.finish(f"{result.cn_name}\n（截图暂时不可用）")

    target = [s for s in sections if s.title.startswith("素材需求") or s.title.startswith("素材")]

    if not target:
        await material_cmd.finish(f"{result.cn_name}\n（未找到素材需求信息）")

    await material_cmd.finish(MessageSegment.image(target[0].png_bytes))
