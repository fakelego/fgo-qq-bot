"""/技能 命令 — 输出从者的主动技能截图（技能1/2/3，含强化前后多版本）"""
from __future__ import annotations

import re

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment, Message
from nonebot.params import CommandArg

from ...services.query.svt_search import query_svt_detail_by_keyword_cn_first
from ...services.wiki_screenshot import capture_servant_sections

skill_cmd = on_command("技能", aliases={"skill", "技能"}, priority=5)


def _cut_tabber_suffix(title: str) -> str:
    """提取 tabber 标签作为显示名，如 '技能2(强化后)' → '强化后'"""
    m = re.search(r'\(([^)]+)\)$', title)
    return m.group(1) if m else ""


_SKILL_PATTERN = re.compile(r'^技能[123]')


def _is_active_skill(title: str) -> bool:
    """只匹配主动技能（技能1/2/3），排除职阶技能、追加技能"""
    return bool(_SKILL_PATTERN.match(title))


@skill_cmd.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    keyword = arg.extract_plain_text().strip()
    if not keyword:
        await skill_cmd.finish("用法：/技能 关键词\n例如：/技能 摩根")

    # 查找从者
    try:
        result = await query_svt_detail_by_keyword_cn_first(keyword)
    except Exception as e:
        await skill_cmd.finish(f"查询失败（网络或数据源异常）：{type(e).__name__}: {e}")

    if not result:
        await skill_cmd.finish(
            f"未命中从者，关键词：{keyword}\n"
            "可先在 plugins/fgo/data/aliases/servant_cn.yaml 添加别名映射"
        )

    # 截取 fgowiki 分节截图
    try:
        sections = await capture_servant_sections(result.cn_name, timeout_ms=15000)
    except Exception:
        sections = []

    if not sections:
        await skill_cmd.finish(f"{result.cn_name}\n（截图暂时不可用，请点击链接查看页面）")

    # 筛选主动技能章节（技能1/2/3，排除职阶技能/追加技能）
    skill_sections = [s for s in sections if _is_active_skill(s.title)]

    if not skill_sections:
        await skill_cmd.finish(f"{result.cn_name}\n（未找到技能信息）")

    # 构建消息：按章节分组，带标签
    msg = Message()
    for i, sec in enumerate(skill_sections):
        # 提取技能基础编号和变体标签
        # 如 "技能2(强化后)" → base="技能2", variant="强化后"
        variant = _cut_tabber_suffix(sec.title)
        base = re.sub(r'\([^)]*\)$', '', sec.title).strip()

        if i > 0:
            msg += MessageSegment.text("\n")

        if variant:
            msg += MessageSegment.text(f"【{base}】{variant}\n")
        else:
            msg += MessageSegment.text(f"【{base}】\n")
        msg += MessageSegment.image(sec.png_bytes)

    await skill_cmd.finish(msg)
