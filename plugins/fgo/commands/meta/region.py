from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent

from ...storage_sqlite import resolve_region

region_cmd = on_command("region", aliases={"区服"}, priority=5)

@region_cmd.handle()
async def _(event: MessageEvent):
    user_id = str(event.user_id)
    group_id = str(event.group_id) if isinstance(event, GroupMessageEvent) else None

    region, source = resolve_region(user_id, group_id)

    source_text = {"group": "群默认", "user": "用户默认", "default": "默认CN"}[source]
    hint = "设置：/setregion cn|jp|tw（用户）"
    if group_id:
        hint += "\n设置群：/setgroupregion cn|jp|tw"

    await region_cmd.finish(
        f"当前生效区服：{region.upper()}（来源：{source_text}）\n{hint}"
    )