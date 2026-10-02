"""/形象 命令 — 输出从者的各阶段图标与战斗形象截图"""
from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment, Message
from nonebot.params import CommandArg

from ...services.query.servant_helper import fetch

appearance_cmd = on_command("形象", aliases={"战斗形象", "立绘", "appearance", "skin"}, priority=5)


@appearance_cmd.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    keyword = arg.extract_plain_text().strip()
    if not keyword:
        await appearance_cmd.finish("用法：/形象 关键词\n例如：/形象 摩根")

    fr = await fetch(keyword)
    if not fr.ok:
        await appearance_cmd.finish(fr.error)

    target = fr.filter(prefix=("各阶段图标", "立绘"))
    if not target:
        await appearance_cmd.finish(f"{fr.cn_name}\n（未找到形象信息）")

    await appearance_cmd.finish(MessageSegment.image(target[0].png_bytes))
