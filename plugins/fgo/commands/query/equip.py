"""/礼装 命令 — 输出礼装截图"""
from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment, Message
from nonebot.params import CommandArg

from ...stores.aliases_equip_cn import find_equip_alias
from ...services.wiki_equip_screenshot import capture_equip_page

equip_cmd = on_command("礼装", aliases={"equip", "ce", "礼装查询"}, priority=5)


@equip_cmd.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    keyword = arg.extract_plain_text().strip()
    if not keyword:
        await equip_cmd.finish("用法：/礼装 关键词\n例如：/礼装 万华镜")

    # 查礼装别名
    hit = find_equip_alias(keyword)
    if not hit:
        await equip_cmd.finish(
            f"未命中礼装，关键词：{keyword}\n"
            "可先在 plugins/fgo/data/aliases/equip_cn.yaml 添加别名映射"
        )

    # 截图
    png = await capture_equip_page(hit.display_name)
    if not png:
        await equip_cmd.finish(f"{hit.display_name}\n（截图暂时不可用）")

    await equip_cmd.finish(MessageSegment.image(png))
