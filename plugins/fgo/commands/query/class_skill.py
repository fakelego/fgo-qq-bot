"""/职阶技能 命令 — 输出从者的职阶技能截图"""
from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment, Message
from nonebot.params import CommandArg

from ...services.query.servant_helper import fetch

class_skill_cmd = on_command("职阶技能", aliases={"职介技能", "classskill", "cs"}, priority=5)


@class_skill_cmd.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    keyword = arg.extract_plain_text().strip()
    if not keyword:
        await class_skill_cmd.finish("用法：/职阶技能 关键词\n例如：/职阶技能 摩根")

    fr = await fetch(keyword)
    if not fr.ok:
        await class_skill_cmd.finish(fr.error)

    target = fr.filter(prefix=("职阶技能", "职介技能"))
    if not target:
        await class_skill_cmd.finish(f"{fr.cn_name}\n（未找到职阶技能信息）")

    await class_skill_cmd.finish(MessageSegment.image(target[0].png_bytes))
