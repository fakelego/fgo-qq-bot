"""/牵绊 命令 — 输出从者的牵绊点数 / 牵绊礼装截图"""
from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment, Message
from nonebot.params import CommandArg

from ...services.query.servant_helper import fetch

bond_cmd = on_command("牵绊", aliases={"牵绊点数", "羁绊", "bond"}, priority=5)


@bond_cmd.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    keyword = arg.extract_plain_text().strip()
    if not keyword:
        await bond_cmd.finish("用法：/牵绊 关键词\n例如：/牵绊 摩根")

    fr = await fetch(keyword)
    if not fr.ok:
        await bond_cmd.finish(fr.error)

    target = fr.filter(prefix="牵绊")
    if not target:
        await bond_cmd.finish(f"{fr.cn_name}\n（未找到牵绊信息）")

    await bond_cmd.finish(MessageSegment.image(target[0].png_bytes))
