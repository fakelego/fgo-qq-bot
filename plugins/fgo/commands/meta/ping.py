from nonebot import on_command

ping = on_command("ping", priority=5)

@ping.handle()
async def _():
    await ping.finish("pong")