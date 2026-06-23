from __future__ import annotations

import time
from nonebot import on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message
from nonebot.params import CommandArg

from ...state import normalize_region
from ...storage_sqlite import set_group_region

setgroupregion = on_command("setgroupregion", aliases={"设置群区服"}, priority=5)

@setgroupregion.handle()
async def _(event: GroupMessageEvent, arg: Message = CommandArg()):
    raw = arg.extract_plain_text().strip()
    r = normalize_region(raw)
    if not r:
        await setgroupregion.finish("用法：/setgroupregion cn|jp|tw\n例如：/setgroupregion cn")

    group_id = str(event.group_id)
    set_group_region(group_id, r, int(time.time()))
    await setgroupregion.finish(f"已设置本群默认区服为：{r.upper()}")