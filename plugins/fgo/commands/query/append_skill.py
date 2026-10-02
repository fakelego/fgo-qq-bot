"""/追加技能 命令 — 输出从者的追加技能截图"""
from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment, Message
from nonebot.params import CommandArg

from ...services.query.servant_helper import fetch

append_skill_cmd = on_command("追加技能", aliases={"appendskill", "as"}, priority=5)


@append_skill_cmd.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    keyword = arg.extract_plain_text().strip()
    if not keyword:
        await append_skill_cmd.finish("用法：/追加技能 关键词\n例如：/追加技能 摩根")

    fr = await fetch(keyword)
    if not fr.ok:
        await append_skill_cmd.finish(fr.error)

    target = fr.filter(prefix="追加技能")
    if not target:
        await append_skill_cmd.finish(f"{fr.cn_name}\n（未找到追加技能信息）")

    await append_skill_cmd.finish(MessageSegment.image(target[0].png_bytes))
