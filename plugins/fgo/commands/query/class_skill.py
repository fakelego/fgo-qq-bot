"""/职阶技能 命令 — 输出从者的职阶技能截图"""
from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment, Message
from nonebot.params import CommandArg

from ...services.query.svt_search import query_svt_detail_by_keyword_cn_first
from ...services.wiki_screenshot import capture_servant_sections

class_skill_cmd = on_command("职阶技能", aliases={"职介技能", "classskill", "cs"}, priority=5)


@class_skill_cmd.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    keyword = arg.extract_plain_text().strip()
    if not keyword:
        await class_skill_cmd.finish("用法：/职阶技能 关键词\n例如：/职阶技能 摩根")

    try:
        result = await query_svt_detail_by_keyword_cn_first(keyword)
    except Exception as e:
        await class_skill_cmd.finish(f"查询失败（网络或数据源异常）：{type(e).__name__}: {e}")

    if not result:
        await class_skill_cmd.finish(
            f"未命中从者，关键词：{keyword}\n"
            "可先在 plugins/fgo/data/aliases/servant_cn.yaml 添加别名映射"
        )

    try:
        sections = await capture_servant_sections(result.cn_name, timeout_ms=15000)
    except Exception:
        sections = []

    if not sections:
        await class_skill_cmd.finish(f"{result.cn_name}\n（截图暂时不可用）")

    # 筛选职阶技能章节
    target = [s for s in sections if s.title.startswith("职阶技能") or s.title.startswith("职介技能")]

    if not target:
        await class_skill_cmd.finish(f"{result.cn_name}\n（未找到职阶技能信息）")

    await class_skill_cmd.finish(MessageSegment.image(target[0].png_bytes))
