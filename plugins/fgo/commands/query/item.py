"""/道具 命令 — 输出素材/道具的 fgowiki 页面截图"""
from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment, Message
from nonebot.params import CommandArg

from ...stores.aliases_material_cn import find_material
from ...services.wiki_material_screenshot import capture_material_page

item_cmd = on_command("道具", aliases={"item", "材料查询", "道具查询"}, priority=5)


@item_cmd.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    keyword = arg.extract_plain_text().strip()
    if not keyword:
        await item_cmd.finish("用法：/道具 关键词\n例如：/道具 英雄之证")

    # 查素材别名
    hit = find_material(keyword)
    if not hit:
        await item_cmd.finish(
            f"未命中道具，关键词：{keyword}\n"
            "可先在 plugins/fgo/data/aliases/material_cn.yaml 添加别名映射"
        )

    # 截图
    png = await capture_material_page(hit.name)
    if not png:
        await item_cmd.finish(f"{hit.name}\n（截图暂时不可用）")

    await item_cmd.finish(MessageSegment.image(png))
