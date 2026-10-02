"""/素材 命令 — 输出从者的灵基再临 / 技能强化素材需求截图"""
from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment, Message
from nonebot.params import CommandArg

from ...services.query.servant_helper import fetch

material_cmd = on_command("素材", aliases={"材料", "素材需求", "material", "mat"}, priority=5)


@material_cmd.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    keyword = arg.extract_plain_text().strip()
    if not keyword:
        await material_cmd.finish("用法：/素材 关键词\n例如：/素材 摩根")

    fr = await fetch(keyword)
    if not fr.ok:
        await material_cmd.finish(fr.error)

    target = fr.filter(prefix=("素材需求", "素材"))
    if not target:
        await material_cmd.finish(f"{fr.cn_name}\n（未找到素材需求信息）")

    await material_cmd.finish(MessageSegment.image(target[0].png_bytes))
