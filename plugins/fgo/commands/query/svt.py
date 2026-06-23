from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageEvent, MessageSegment
from nonebot.params import CommandArg

from ...render.svt_mooncell import render_svt_base_table
from ...services.query.svt_search import query_svt_detail_by_keyword_cn_first
from ...state import normalize_region
from ...storage_sqlite import resolve_region

svt = on_command("svt", aliases={"从者"}, priority=5)


@svt.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    text = arg.extract_plain_text().strip()
    if not text:
        await svt.finish("用法：/svt [cn|jp|tw] 关键词\n例如：/svt 摩根")

    parts = text.split(maxsplit=1)

    explicit_region = None
    keyword = text
    if len(parts) == 2:
        maybe_region = normalize_region(parts[0])
        if maybe_region:
            explicit_region = maybe_region
            keyword = parts[1].strip()

    user_id = str(event.user_id)
    group_id = str(event.group_id) if isinstance(event, GroupMessageEvent) else None

    if explicit_region:
        region = explicit_region
        source = "explicit"
    else:
        region, source = resolve_region(user_id, group_id)

    try:
        result = await query_svt_detail_by_keyword_cn_first(keyword)
    except Exception as e:
        await svt.finish(f"查询失败（网络或数据源异常）：{type(e).__name__}: {e}")

    if not result:
        await svt.finish(
            "未命中从者（当前使用：本地国服别名表 -> Atlas 结构化数据）\n"
            f"关键词：{keyword}\n"
            "你可以先在 aliases 文件里加一条映射：\n"
            "plugins/fgo/data/aliases/servant_cn.yaml\n"
        )

    # 渲染 Mooncell 风格图片
    try:
        png = await render_svt_base_table(result.detail)
    except Exception as e:
        await svt.finish(f"渲染失败：{type(e).__name__}: {e}")

    source_text = {
        "explicit": "显式指定",
        "group": "群默认",
        "user": "用户默认",
        "default": "默认CN",
    }.get(source, "未知")

    caption = f"{result.cn_name}  {region.upper()}（{source_text}）"
    if result.mooncell_url:
        caption += f"\n🔗 {result.mooncell_url}"

    await svt.finish(MessageSegment.image(png) + MessageSegment.text(caption))
