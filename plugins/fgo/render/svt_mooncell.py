# plugins/fgo/render/svt_mooncell.py
"""Mooncell 风格从者信息图渲染器"""
from __future__ import annotations

from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from ..services.assets import fetch_image_bytes
from ..stores.atlas_client import _get_session

# ===== 画布与调色板 =====
W, H = 1140, 897
C_LIGHT = (248, 249, 250)
C_STRIPE = (234, 235, 238)
C_GRID = (162, 169, 177)
C_HEAD = (234, 235, 238)
C_TEXT = (32, 33, 34)
C_SUB = (117, 116, 120)
C_BLUE = (6, 69, 173)
C_WHITE = (255, 255, 255)
C_GOLD = (180, 140, 40)

# 布局: 左侧面板 LX..RX, 右侧面板从 RIGHT_X 开始
LX, RX = 30, 748
RIGHT_X, RIGHT_W = 764, 346
RIGHT_X2 = RIGHT_X + RIGHT_W
HPAD = 14  # 内边距

CARD_LETTER = {"1": "A", "2": "B", "3": "Q"}
CARD_COLORS = {
    "A": ((42, 120, 210), (28, 90, 170)),
    "B": ((210, 70, 70), (170, 45, 45)),
    "Q": ((42, 160, 80), (18, 120, 55)),
}
ATTR_MAP = {"earth": "地", "sky": "天", "human": "人", "star": "星", "beast": "兽"}

CLASS_COLORS = {
    "SABER": (74, 43, 34), "ARCHER": (67, 128, 194), "LANCER": (42, 160, 80),
    "RIDER": (95, 163, 229), "CASTER": (116, 56, 34), "ASSASSIN": (130, 95, 75),
    "BERSERKER": (157, 88, 41), "RULER": (234, 184, 118), "AVENGER": (52, 33, 55),
    "ALTEREGO": (220, 154, 75), "MOONCANCER": (32, 115, 187),
    "FOREIGNER": (32, 77, 152), "PRETENDER": (109, 47, 34),
    "SHIELDER": (88, 132, 181), "BEAST": (185, 115, 34),
}


def _font(size: int):
    for p in [
        "plugins/fgo/data/fonts/NotoSansCJKsc-Regular.otf",
        "plugins/fgo/data/fonts/SourceHanSansSC-Regular.otf",
    ]:
        try:
            return ImageFont.truetype(p, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def fit_cover(im: Image.Image, box_w: int, box_h: int) -> Image.Image:
    im = im.convert("RGBA")
    iw, ih = im.size
    if iw == 0 or ih == 0:
        return Image.new("RGBA", (box_w, box_h), (245, 245, 245, 255))
    scale = max(box_w / iw, box_h / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    resized = im.resize((nw, nh), Image.Resampling.LANCZOS)
    x0 = (nw - box_w) // 2
    y0 = (nh - box_h) // 2
    return resized.crop((x0, y0, x0 + box_w, y0 + box_h))


def _stat(level: int, base, maxv, lv_max, growth):
    if level == 1:
        return base
    if lv_max == level and maxv is not None:
        return int(maxv)
    if growth and len(growth) >= level:
        return int(growth[level - 1])
    return None


def draw_card(d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, letter: str, font):
    letter = (letter or "?").upper()
    fill, border = CARD_COLORS.get(letter, ((150, 150, 150), (120, 120, 120)))
    r = max(4, min(w, h) // 6)
    d.rounded_rectangle((x, y, x + w, y + h), radius=r, fill=fill, outline=border, width=2)
    d.rounded_rectangle((x + 3, y + 3, x + w - 3, y + h // 3), radius=max(1, r - 2),
                        fill=(255, 255, 255, 35))
    tw = d.textlength(letter, font=font)
    d.text((x + (w - tw) / 2, y + (h - font.size) / 2 - 2), letter, font=font, fill=(255, 255, 255, 230))


def _stripe_bg(d: ImageDraw.ImageDraw, y: int, h: int, index: int, x1: int = LX, x2: int = RX):
    """绘制交替条纹背景"""
    bg = C_STRIPE if index % 2 == 1 else C_LIGHT
    d.rectangle((x1, y, x2, y + h), fill=bg)


async def render_svt_base_table(detail: dict[str, Any]) -> bytes:
    img = Image.new("RGBA", (W, H), C_LIGHT)
    d = ImageDraw.Draw(img)

    ft = _font(24)
    fn = _font(19)
    fb = _font(14)
    fs = _font(12)
    fm = _font(15)
    fc = _font(24)

    # --- 数据 ---
    name = str(detail.get("name") or "")
    cno = int(detail.get("collectionNo") or 0)
    rarity = int(detail.get("rarity") or 0)
    cost = int(detail.get("cost") or 0)
    cls = str(detail.get("className") or "").upper()
    attr = ATTR_MAP.get(str(detail.get("attribute") or ""), str(detail.get("attribute") or ""))
    cls_color = CLASS_COLORS.get(cls, (100, 100, 100))

    atk_base = detail.get("atkBase")
    atk_max = detail.get("atkMax")
    hp_base = detail.get("hpBase")
    hp_max = detail.get("hpMax")
    lv_max = detail.get("lvMax")
    atk_g = detail.get("atkGrowth") or []
    hp_g = detail.get("hpGrowth") or []

    cards = detail.get("cards") or []
    letters = [CARD_LETTER.get(str(x), "?") for x in cards][:5]

    # ===================================================================
    # 1. 顶部全宽标题栏
    # ===================================================================
    full_w = RIGHT_X2 - LX  # LX 到右侧面板右端
    top_y, top_h = 8, 66
    d.rectangle((LX, top_y, RIGHT_X2, top_y + top_h), fill=C_WHITE, outline=C_GRID, width=1)

    # 职阶色块
    blk_w, blk_h = 36, 46
    d.rectangle((LX + 10, top_y + 10, LX + 10 + blk_w, top_y + 10 + blk_h), fill=cls_color)
    # 职阶名 + 从者名
    d.text((LX + 56, top_y + 8), cls, font=_font(17), fill=C_TEXT)
    d.text((LX + 56, top_y + 34), name, font=fn, fill=C_TEXT)
    # 星级
    stars_str = "★" * rarity
    tw = d.textlength(stars_str, font=_font(16))
    d.text((RIGHT_X2 - tw - 16, top_y + 10), stars_str, font=_font(16), fill=C_GOLD)

    # ===================================================================
    # 2. 基础信息行
    # ===================================================================
    info_y = top_y + top_h + 6
    info_h = 46
    d.rectangle((LX, info_y, RX, info_y + info_h), fill=C_WHITE, outline=C_GRID, width=1)

    col_w = (RX - LX) // 4
    labels = ["COST", "稀有度", "职阶", "属性"]
    values = [str(cost), f"★{rarity}", cls, attr]
    for i in range(4):
        x1, x2 = LX + i * col_w, LX + (i + 1) * col_w
        if i > 0:
            d.line((x1, info_y, x1, info_y + info_h), fill=C_GRID, width=1)
        d.rectangle((x1, info_y, x2, info_y + 20), fill=C_HEAD)
        d.text((x1 + 10, info_y + 2), labels[i], font=fs, fill=C_SUB)
        d.text((x1 + 10, info_y + 24), values[i], font=fb, fill=C_TEXT)

    # ===================================================================
    # 3. ATK/HP 数值表
    # ===================================================================
    tbl_y = info_y + info_h + 6
    # 列: Label | Lv.1 | Lv.90 | Lv.100 | Lv.120
    col_defs = [
        ("", 70),
        ("Lv.1", 130),
        ("Lv.90", 130),
        ("Lv.100", 130),
        ("Lv.120", 130),
    ]
    col_x = [LX]
    for _, cw in col_defs:
        col_x.append(col_x[-1] + cw)
    scale = (RX - LX) / (col_x[-1] - LX)
    col_x = [int(LX + (x - LX) * scale) for x in col_x]

    # 表头
    d.rectangle((LX, tbl_y, RX, tbl_y + 30), fill=C_HEAD)
    for i, (hdr, _) in enumerate(col_defs):
        x1, x2 = col_x[i], col_x[i + 1]
        if i > 0:
            d.line((x1, tbl_y, x1, tbl_y + 30), fill=C_GRID, width=1)
        if hdr:
            tw = d.textlength(hdr, font=fs)
            d.text((x1 + (x2 - x1 - tw) / 2, tbl_y + 7), hdr, font=fs, fill=C_SUB)

    def fmt(v):
        return "—" if v is None else str(v)

    row_h = 32
    cur_y = tbl_y + 30

    # ATK 行组
    for li, lv in enumerate([1, 90, 100, 120]):
        val = _stat(lv, atk_base, atk_max, lv_max, atk_g)
        _stripe_bg(d, cur_y, row_h, li)
        d.line((LX, cur_y, RX, cur_y), fill=C_GRID, width=1)
        if li == 0:
            d.text((LX + 8, cur_y + 8), "ATK", font=fb, fill=C_TEXT)
        # 数值放在对应列
        xv1, xv2 = col_x[li + 1], col_x[li + 2]
        v = fmt(val)
        tw = d.textlength(v, font=fm)
        d.text((xv1 + (xv2 - xv1 - tw) / 2, cur_y + 7), v, font=fm, fill=C_TEXT)
        cur_y += row_h

    # HP 行组
    for li, lv in enumerate([1, 90, 100, 120]):
        val = _stat(lv, hp_base, hp_max, lv_max, hp_g)
        _stripe_bg(d, cur_y, row_h, li + 4)
        d.line((LX, cur_y, RX, cur_y), fill=C_GRID, width=1)
        if li == 0:
            d.text((LX + 8, cur_y + 8), "HP", font=fb, fill=C_TEXT)
        xv1, xv2 = col_x[li + 1], col_x[li + 2]
        v = fmt(val)
        tw = d.textlength(v, font=fm)
        d.text((xv1 + (xv2 - xv1 - tw) / 2, cur_y + 7), v, font=fm, fill=C_TEXT)
        cur_y += row_h

    d.line((LX, cur_y, RX, cur_y), fill=C_GRID, width=1)

    # ===================================================================
    # 4. 指令卡区域
    # ===================================================================
    card_y = cur_y + 10
    d.rectangle((LX, card_y, LX + 80, card_y + 28), fill=C_HEAD)
    d.text((LX + 8, card_y + 5), "指令卡", font=fs, fill=C_SUB)

    cw, ch = 64, 64
    cg = 8
    cx0 = LX + 96
    for i, lt in enumerate(letters):
        cx = cx0 + i * (cw + cg)
        draw_card(d, cx, card_y - 2, cw, ch, lt, fc)

    # 卡 hit 信息
    card_details = detail.get("cardDetails") or {}
    hit_y = card_y + ch + 4
    if isinstance(card_details, dict):
        for i, key in enumerate(sorted(card_details.keys(), key=int)[:5]):
            cd = card_details[key]
            hits = cd.get("hitsDistribution") or []
            total_hits = sum(hits) if isinstance(hits, list) else 0
            if total_hits > 0:
                lt = letters[i] if i < len(letters) else "?"
                d.text((cx0 + i * (cw + cg) + 8, hit_y), f"{lt} {total_hits}hits", font=_font(10), fill=C_SUB)

    # ===================================================================
    # 5. 宝具
    # ===================================================================
    np_list = detail.get("noblePhantasms") or []
    np_y = card_y + ch + 22

    if np_list:
        np_data = np_list[0]
        np_name = str(np_data.get("name") or "")
        np_type = str(np_data.get("card") or "")
        np_type_cn = {"1": "Arts", "2": "Buster", "3": "Quick"}.get(np_type, np_type)
        np_rank = str(np_data.get("rank") or "")
        np_hits = np_data.get("npHits") or ""

        d.rectangle((LX, np_y, LX + 80, np_y + 26), fill=C_HEAD)
        d.text((LX + 8, np_y + 4), "宝具", font=fs, fill=C_SUB)

        # NP 色标
        np_color = {"1": (42, 120, 210), "2": (210, 70, 70), "3": (42, 160, 80)}.get(np_type, (100, 100, 100))
        d.rectangle((LX + 10, np_y + 34, LX + 26, np_y + 50), fill=np_color)
        d.text((LX + 34, np_y + 32), f"{np_name}  {np_rank}", font=fb, fill=C_TEXT)
        d.text((LX + 34, np_y + 50), f"类型: {np_type_cn}  Hits: {np_hits}", font=fs, fill=C_SUB)

    # ===================================================================
    # 6. 技能
    # ===================================================================
    skills = detail.get("skills") or []
    sk_y = np_y + 72 if np_list else np_y

    d.rectangle((LX, sk_y, LX + 80, sk_y + 26), fill=C_HEAD)
    d.text((LX + 8, sk_y + 4), "保有技能", font=fs, fill=C_SUB)

    for si, skill in enumerate(skills[:3]):
        sy = sk_y + 26 + si * 38
        _stripe_bg(d, sy, 38, si)
        d.line((LX, sy, RX, sy), fill=C_GRID, width=1)
        s_name = str(skill.get("name") or "")
        s_detail = str(skill.get("detail") or "")
        if len(s_detail) > 55:
            s_detail = s_detail[:52] + "..."
        d.text((LX + 10, sy + 4), s_name, font=fb, fill=C_TEXT)
        if s_detail:
            d.text((LX + 10, sy + 20), s_detail, font=fs, fill=C_SUB)

    sk_bottom = sk_y + 26 + len(skills[:3]) * 38
    d.line((LX, sk_bottom, RX, sk_bottom), fill=C_GRID, width=1)

    # ===================================================================
    # 7. 追加技能
    # ===================================================================
    append_skills = detail.get("appendPassive") or []
    if append_skills:
        ap_y = sk_bottom + 6
        d.rectangle((LX, ap_y, LX + 80, ap_y + 26), fill=C_HEAD)
        d.text((LX + 8, ap_y + 4), "追加技能", font=fs, fill=C_SUB)
        for ai, askill in enumerate(append_skills[:3]):
            ay = ap_y + 26 + ai * 38
            _stripe_bg(d, ay, 38, ai)
            d.line((LX, ay, RX, ay), fill=C_GRID, width=1)
            ask = askill.get("skill") or askill
            a_name = str(ask.get("name") or "")
            a_detail = str(ask.get("detail") or "")
            if len(a_detail) > 55:
                a_detail = a_detail[:52] + "..."
            d.text((LX + 10, ay + 4), a_name, font=fb, fill=C_TEXT)
            if a_detail:
                d.text((LX + 10, ay + 20), a_detail, font=fs, fill=C_SUB)
        ap_bottom = ap_y + 26 + len(append_skills[:3]) * 38
    else:
        ap_bottom = sk_bottom

    # ===================================================================
    # 8. 右侧面板
    # ===================================================================
    r_panel_y1 = info_y
    r_panel_y2 = H - 50

    d.rectangle((RIGHT_X, r_panel_y1, RIGHT_X2, r_panel_y2), fill=C_WHITE, outline=C_GRID, width=1)

    pad = HPAD
    rx = RIGHT_X + pad
    ry = r_panel_y1 + pad

    # No. + 星级
    d.text((rx, ry), f"No.{cno}", font=_font(20), fill=C_TEXT)
    d.text((rx, ry + 28), "★" * rarity, font=_font(17), fill=C_GOLD)

    # 职阶色块
    d.rectangle((rx, ry + 50, rx + 34, ry + 80), fill=cls_color)
    d.text((rx + 42, ry + 56), cls, font=fs, fill=C_SUB)

    # 立绘区域（控制高度避免过大）
    art_x1 = RIGHT_X + 6
    art_y1 = ry + 100
    art_x2 = RIGHT_X2 - 6
    art_y2 = ry + 460  # 固定 360px 高

    d.rectangle((art_x1, art_y1, art_x2, art_y2), outline=C_GRID, width=1, fill=(246, 247, 249))

    # 立绘
    assets = detail.get("extraAssets") or detail.get("extra") or {}
    cg_urls = (assets.get("charaGraph") or {}).get("ascension") or {}
    cg_url = cg_urls.get("4") or cg_urls.get("3") or cg_urls.get("2") or cg_urls.get("1")
    if cg_url:
        try:
            sess = await _get_session()
            b = await fetch_image_bytes(sess, cg_url)
            art = Image.open(BytesIO(b)).convert("RGBA")
            bw = art_x2 - art_x1 - 2
            bh = art_y2 - art_y1 - 2
            art = fit_cover(art, bw, bh)
            img.paste(art, (art_x1 + 1, art_y1 + 1), art)
        except Exception:
            pass

    # 右侧底部指令卡
    bot_cw, bot_ch = 44, 44
    bot_gap = 5
    bot_total = len(letters) * bot_cw + (len(letters) - 1) * bot_gap
    bot_x0 = RIGHT_X + (RIGHT_W - bot_total) // 2
    bot_y = art_y2 + 12
    for i, lt in enumerate(letters):
        cx = bot_x0 + i * (bot_cw + bot_gap)
        draw_card(d, cx, bot_y, bot_cw, bot_ch, lt, _font(16))

    # ===================================================================
    # 9. Footer
    # ===================================================================
    footer = "数据来源：Atlas Academy / Mooncell  |  fgo.wiki"
    ff = _font(13)
    tw = d.textlength(footer, font=ff)
    d.text(((W - tw) / 2, H - 32), footer, font=ff, fill=C_SUB)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
