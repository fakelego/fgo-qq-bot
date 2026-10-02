from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent

help_cmd = on_command("help", aliases={"帮助"}, priority=5)


@help_cmd.handle()
async def _(event: MessageEvent):
    msg = (
        "FGO Bot 指令：\n"
        "—— 从者查询 ——\n"
        "/查询 关键词  从者基础信息\n"
        "/宝具 关键词  宝具（含强化前后）\n"
        "/技能 关键词  主动技能\n"
        "/职阶技能 关键词  职阶技能\n"
        "/追加技能 关键词  追加技能\n"
        "/素材 关键词  灵基再临/技能强化素材\n"
        "/牵绊 关键词  牵绊点数/牵绊礼装\n"
        "/资料 关键词  角色详情\n"
        "/资料1~6 关键词  个人资料1~6\n"
        "/形象 关键词  各阶段图标与战斗形象\n"
        "/卡面 关键词 [1-4|灵衣]  卡面立绘\n"
        "—— 礼装与素材 ——\n"
        "/礼装 关键词  礼装信息\n"
        "/道具 关键词  素材信息\n"
        "/刷取 关键词  高效掉落关卡\n"
        "—— 其他 ——\n"
        "/ping  健康检查\n"
        "/help  查看帮助\n"
    )
    await help_cmd.finish(msg)
