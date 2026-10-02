"""/刷取 命令 — 输出素材/道具的主要掉落关卡表截图"""
from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment, Message
from nonebot.params import CommandArg

from ...stores.aliases_material_cn import find_material
from ...services.wiki_material_screenshot import capture_material_farming

farm_cmd = on_command("刷取", aliases={"farm", "掉落", "刷材料", "去哪刷"}, priority=5)


@farm_cmd.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    keyword = arg.extract_plain_text().strip()
    if not keyword:
        await farm_cmd.finish("用法：/刷取 关键词\n例如：/刷取 英雄之证")

    hit = find_material(keyword)
    if not hit:
        await farm_cmd.finish(
            f"未命中道具，关键词：{keyword}\n"
            "可先在 plugins/fgo/data/aliases/material_cn.yaml 添加别名映射"
        )

    png = await capture_material_farming(hit.name)
    if not png:
        await farm_cmd.finish(f"{hit.name}\n（掉落关卡表暂时不可用）")

    await farm_cmd.finish(MessageSegment.image(png))
