from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent

from ...storage_sqlite import resolve_region

help_cmd = on_command("help", aliases={"帮助"}, priority=5)

@help_cmd.handle()
async def _(event: MessageEvent):
    user_id = str(event.user_id)
    group_id = str(event.group_id) if isinstance(event, GroupMessageEvent) else None
    region, source = resolve_region(user_id, group_id)

    msg = (
        "FGO Bot 指令：\n"
        f"- /region  查看当前生效区服（当前：{region.upper()}）\n"
        "- /setregion cn|jp|tw  设置你的默认区服\n"
    )
    if group_id:
        msg += "- /setgroupregion cn|jp|tw  设置本群默认区服\n"
    msg += (
        "- /ping  健康检查\n"
        "\n"
        "后续将支持（待实现）：\n"
        "- /svt [cn|jp|tw] 关键词  查询从者\n"
        "- /ce  [cn|jp|tw] 关键词  查询礼装\n"
        "- /mat [cn|jp|tw] 关键词  查询材料\n"
        "- /guide [cn|jp|tw] 关键词  查询攻略链接\n"
    )
    await help_cmd.finish(msg)