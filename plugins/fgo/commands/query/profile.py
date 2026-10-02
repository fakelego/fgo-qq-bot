"""/资料 命令 — /资料 输出角色详情；/资料1~/资料6 输出个人资料1~6"""
from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment, Message
from nonebot.params import CommandArg

from ...services.query.servant_helper import fetch


# ── /资料 → 角色详情 ──────────────────────────────────────
profile_cmd = on_command("资料", aliases={"profile"}, priority=5)


@profile_cmd.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    keyword = arg.extract_plain_text().strip()
    if not keyword:
        await profile_cmd.finish("用法：/资料 关键词\n例如：/资料 摩根")

    fr = await fetch(keyword)
    if not fr.ok:
        await profile_cmd.finish(fr.error)

    target = fr.filter(exact="资料(角色详情)")
    if not target:
        await profile_cmd.finish(f"{fr.cn_name}\n（未找到角色详情）")

    await profile_cmd.finish(MessageSegment.image(target[0].png_bytes))


# ── /资料1 ~ /资料6 → 个人资料1~6 ───────────────────────────

def _make_profile_handler(n: int):
    """生成第 n 个个人资料的 handler（n=1~6）"""

    async def handler(event: MessageEvent, arg: Message = CommandArg()):
        keyword = arg.extract_plain_text().strip()
        if not keyword:
            await handler._matcher.finish(f"用法：/资料{n} 关键词")

        fr = await fetch(keyword)
        if not fr.ok:
            await handler._matcher.finish(fr.error)

        label = f"资料(个人资料{n})"
        target = fr.filter(exact=label)
        if not target:
            await handler._matcher.finish(f"{fr.cn_name}\n（未找到「{label}」）")

        await handler._matcher.finish(MessageSegment.image(target[0].png_bytes))

    return handler


for _n in range(1, 7):
    _cmd = on_command(f"资料{_n}", priority=5)
    _h = _make_profile_handler(_n)
    _h._matcher = _cmd
    _cmd.handle()(_h)
