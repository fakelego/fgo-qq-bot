"""/卡面 命令 — 输出从者的卡面立绘图片（支持阶段1-4和灵衣）"""
from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment, Message
from nonebot.params import CommandArg

from ...services.query.svt_search import query_svt_detail_by_keyword_cn_first
from ...services.wiki_card import get_servant_card_image

card_cmd = on_command("卡面", aliases={"card", "卡面"}, priority=5)

_VALID_SPECS = frozenset({"1", "2", "3", "4", "灵衣"})


def _parse_args(raw: str) -> tuple[str, str]:
    """从用户输入中拆解从者关键词和阶段编号。

    /卡面 呆毛 1      → ("呆毛", "1")
    /卡面 呆毛 灵衣   → ("呆毛", "灵衣")
    /卡面 呆毛        → ("呆毛", "1")   # 默认阶段1
    """
    parts = raw.strip().split()
    if not parts:
        return "", "1"

    if parts[-1] in _VALID_SPECS:
        keyword = " ".join(parts[:-1])
        spec = parts[-1]
    else:
        keyword = " ".join(parts)
        spec = "1"

    return keyword, spec


@card_cmd.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    # ── 段1：参数解析 ──────────────────────────────────────────
    raw = arg.extract_plain_text().strip()
    if not raw:
        await card_cmd.finish(
            "用法：/卡面 关键词 [1-4|灵衣]\n"
            "例如：/卡面 呆毛 1\n"
            "      /卡面 呆毛 灵衣\n"
            "      阶段1=初始, 阶段2=一破, 阶段3=三破, 阶段4=满破"
        )

    keyword, spec = _parse_args(raw)

    # ── 段2：查询从者 ──────────────────────────────────────────
    try:
        result = await query_svt_detail_by_keyword_cn_first(keyword)
    except Exception as e:
        await card_cmd.finish(f"查询失败（网络或数据源异常）：{type(e).__name__}: {e}")

    if not result:
        await card_cmd.finish(
            f"未命中从者，关键词：{keyword}\n"
            "可先在 plugins/fgo/data/aliases/servant_cn.yaml 添加别名映射"
        )

    # ── 段3：获取卡面图片 ──────────────────────────────────────
    try:
        png = await get_servant_card_image(result.cn_name, spec, timeout_ms=15000)
    except Exception:
        png = None

    if not png:
        label = {"1": "阶段1", "2": "阶段2", "3": "阶段3", "4": "阶段4"}.get(spec, spec)
        await card_cmd.finish(f"{result.cn_name} {label}\n（卡面图片暂时不可用）")

    # ── 段4：发送图片 ──────────────────────────────────────────
    await card_cmd.finish(MessageSegment.image(png))
