"""/宝具 命令 — 输出从者的宝具截图（含强化前后多版本）"""
from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment, Message
from nonebot.params import CommandArg

from ...services.query.svt_search import query_svt_detail_by_keyword_cn_first
from ...services.wiki_screenshot import capture_servant_sections

np_cmd = on_command("宝具", aliases={"np", "NP", "宝具"}, priority=5)


def _cut_tabber_suffix(title: str) -> str:
    """提取 tabber 标签作为显示名，如 '宝具(强化后)' → '强化后'"""
    import re
    m = re.search(r'\(([^)]+)\)$', title)
    return m.group(1) if m else title


@np_cmd.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    keyword = arg.extract_plain_text().strip()
    if not keyword:
        await np_cmd.finish("用法：/宝具 关键词\n例如：/宝具 摩根")

    # 查找从者
    try:
        result = await query_svt_detail_by_keyword_cn_first(keyword)
    except Exception as e:
        await np_cmd.finish(f"查询失败（网络或数据源异常）：{type(e).__name__}: {e}")

    if not result:
        await np_cmd.finish(
            f"未命中从者，关键词：{keyword}\n"
            "可先在 plugins/fgo/data/aliases/servant_cn.yaml 添加别名映射"
        )

    # 截取 fgowiki 分节截图
    try:
        sections = await capture_servant_sections(result.cn_name, timeout_ms=15000)
    except Exception:
        sections = []

    if not sections:
        await np_cmd.finish(f"{result.cn_name}\n（截图暂时不可用，请点击链接查看页面）")

    # 筛选宝具相关章节
    np_sections = [s for s in sections if s.title.startswith("宝具")]

    if not np_sections:
        await np_cmd.finish(f"{result.cn_name}\n（未找到宝具信息）")

    # 发送：多版本时每条带标签，单版本纯图片
    if len(np_sections) == 1:
        await np_cmd.finish(MessageSegment.image(np_sections[0].png_bytes))

    # 多版本 — 逐条发送，最后 finish
    msg = Message()
    for i, sec in enumerate(np_sections):
        label = _cut_tabber_suffix(sec.title)
        if i > 0:
            msg += MessageSegment.text("\n")
        msg += MessageSegment.text(f"【{label}】\n")
        msg += MessageSegment.image(sec.png_bytes)
    await np_cmd.finish(msg)
