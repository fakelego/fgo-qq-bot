"""/宝具 命令 — 输出从者的宝具截图（含强化前后多版本）"""
from __future__ import annotations

import re

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment, Message
from nonebot.params import CommandArg

from ...services.query.servant_helper import fetch

np_cmd = on_command("宝具", aliases={"np", "NP", "宝具"}, priority=5)


def _cut_tabber_suffix(title: str) -> str:
    """提取 tabber 标签作为显示名，如 '宝具(强化后)' → '强化后'"""
    m = re.search(r'\(([^)]+)\)$', title)
    return m.group(1) if m else title


@np_cmd.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    keyword = arg.extract_plain_text().strip()
    if not keyword:
        await np_cmd.finish("用法：/宝具 关键词\n例如：/宝具 摩根")

    fr = await fetch(keyword)
    if not fr.ok:
        await np_cmd.finish(fr.error)

    np_sections = fr.filter(prefix="宝具")
    if not np_sections:
        await np_cmd.finish(f"{fr.cn_name}\n（未找到宝具信息）")

    # 单版本 → 纯图片；多版本 → 逐条带标签
    if len(np_sections) == 1:
        await np_cmd.finish(MessageSegment.image(np_sections[0].png_bytes))

    msg = Message()
    for i, sec in enumerate(np_sections):
        label = _cut_tabber_suffix(sec.title)
        if i > 0:
            msg += MessageSegment.text("\n")
        msg += MessageSegment.text(f"【{label}】\n")
        msg += MessageSegment.image(sec.png_bytes)
    await np_cmd.finish(msg)
