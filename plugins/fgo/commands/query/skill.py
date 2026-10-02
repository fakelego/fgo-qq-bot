"""/技能 命令 — 输出从者的主动技能截图（技能1/2/3，含强化前后多版本）"""
from __future__ import annotations

import re

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment, Message
from nonebot.params import CommandArg

from ...services.query.servant_helper import fetch

skill_cmd = on_command("技能", aliases={"skill", "技能"}, priority=5)

_SKILL_PATTERN = re.compile(r'^技能[123]')


def _cut_tabber_suffix(title: str) -> str:
    """提取 tabber 标签作为显示名，如 '技能2(强化后)' → '强化后'"""
    m = re.search(r'\(([^)]+)\)$', title)
    return m.group(1) if m else ""


@skill_cmd.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    keyword = arg.extract_plain_text().strip()
    if not keyword:
        await skill_cmd.finish("用法：/技能 关键词\n例如：/技能 摩根")

    fr = await fetch(keyword)
    if not fr.ok:
        await skill_cmd.finish(fr.error)

    skill_sections = fr.filter(pattern=_SKILL_PATTERN)
    if not skill_sections:
        await skill_cmd.finish(f"{fr.cn_name}\n（未找到技能信息）")

    msg = Message()
    for i, sec in enumerate(skill_sections):
        variant = _cut_tabber_suffix(sec.title)
        base = re.sub(r'\([^)]*\)$', '', sec.title).strip()

        if i > 0:
            msg += MessageSegment.text("\n")
        if variant:
            msg += MessageSegment.text(f"【{base}】{variant}\n")
        else:
            msg += MessageSegment.text(f"【{base}】\n")
        msg += MessageSegment.image(sec.png_bytes)

    await skill_cmd.finish(msg)
