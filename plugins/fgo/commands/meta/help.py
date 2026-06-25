from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent

help_cmd = on_command("help", aliases={"帮助"}, priority=5)


@help_cmd.handle()
async def _(event: MessageEvent):
    msg = (
        "FGO Bot 指令：\n"
        "- /查询 关键词  查询从者基础数值\n"
        "- /ping  健康检查\n"
        "- /help  查看帮助\n"
    )
    await help_cmd.finish(msg)
