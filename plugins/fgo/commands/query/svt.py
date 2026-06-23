from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, Message
from nonebot.params import CommandArg

from ...storage_sqlite import resolve_region
from ...state import normalize_region
from ...services.query.svt_search import query_svt_detail_by_keyword_cn_first

from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, Message, MessageSegment
from ...services.query.svt_search import query_svt_detail_by_keyword_cn_first
from ...render.svt_mooncell import render_svt_base_table

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

    # 当前这版：以国服体验为主，但“结构化字段”来自 Atlas（JP）。
    # 因此 region 先仅用于显示/未来扩展（比如不同别名表、不同活动名等）。
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

     # 渲染
        try:
            png = await render_svt_base_table(result.detail)
        except Exception as e:
            await svt.finish(f"渲染失败：{type(e).__name__}: {e}")

        await svt.finish(MessageSegment.image(png))

    atlas = result.atlas
    cn_name = result.cn_name or keyword
    moon = result.mooncell_url or ""

    source_text = {
        "explicit": "显式指定",
        "group": "群默认",
        "user": "用户默认",
        "default": "默认CN",
    }.get(source, "未知")

    msg = (
        f"从者：{cn_name}\n"
        f"区服：{region.upper()}（来源：{source_text}）\n"
        f"职阶：{atlas.className}  星级：{atlas.rarity}★\n"
        f"AtlasID：{atlas.id}"
    )
    if atlas.collectionNo is not None:
        msg += f"  CollectionNo：{atlas.collectionNo}"
    if moon:
        msg += f"\nMooncell：{moon}"

    await svt.finish(msg)