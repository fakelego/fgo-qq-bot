"""/查询 命令 — 从者基础信息查询（主命令）"""
from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageEvent, MessageSegment
from nonebot.params import CommandArg

from ...services.query.servant_helper import fetch

svt = on_command("查询", aliases={"svt", "从者"}, priority=5)


@svt.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    keyword = arg.extract_plain_text().strip()
    if not keyword:
        await svt.finish("用法：/查询 关键词\n例如：/查询 摩根")

    fr = await fetch(keyword)
    if not fr.ok:
        await svt.finish(fr.error)

    # 只发第一张截图
    await svt.finish(MessageSegment.image(fr.sections[0].png_bytes))
