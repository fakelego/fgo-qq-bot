from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageEvent, MessageSegment
from nonebot.params import CommandArg

from ...services.query.svt_search import query_svt_detail_by_keyword_cn_first
from ...services.wiki_screenshot import capture_servant_sections

svt = on_command("查询", aliases={"svt", "从者"}, priority=5)


@svt.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    keyword = arg.extract_plain_text().strip()
    if not keyword:
        await svt.finish("用法：/查询 关键词\n例如：/查询 摩根")

    # 查从者
    try:
        result = await query_svt_detail_by_keyword_cn_first(keyword)
    except Exception as e:
        await svt.finish(f"查询失败（网络或数据源异常）：{type(e).__name__}: {e}")

    if not result:
        await svt.finish(
            "未命中从者（当前使用：本地国服别名表 → Atlas 结构化数据）\n"
            f"关键词：{keyword}\n"
            "你可以先在 aliases 文件里加一条映射：\n"
            "plugins/fgo/data/aliases/servant_cn.yaml\n"
        )

    # 截取 fgowiki 分节截图
    header = f"{result.cn_name}"
    if result.mooncell_url:
        header += f"\n🔗 {result.mooncell_url}"

    try:
        sections = await capture_servant_sections(result.cn_name, timeout_ms=15000)
    except Exception:
        sections = []

    if not sections:
        await svt.finish(header + "\n（截图暂时不可用，请点击链接查看页面）")

    # 只发第一张截图
    first = sections[0]
    await svt.finish(MessageSegment.image(first.png_bytes))
