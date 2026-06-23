from __future__ import annotations

import time
from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, Message
from nonebot.params import CommandArg

from ...state import normalize_region
from ...storage_sqlite import set_user_region

setregion = on_command("setregion", aliases={"设置区服"}, priority=5)

@setregion.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    raw = arg.extract_plain_text().strip()
    r = normalize_region(raw)
    if not r:
        await setregion.finish("用法：/setregion cn|jp|tw\n例如：/setregion jp")

    user_id = str(event.user_id)
    set_user_region(user_id, r, int(time.time()))
    await setregion.finish(f"已设置你的默认区服为：{r.upper()}")