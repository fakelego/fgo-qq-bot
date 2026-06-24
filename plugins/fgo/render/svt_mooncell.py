# plugins/fgo/render/svt_mooncell.py
"""fgowiki 风格从者信息图渲染器"""
from __future__ import annotations

from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from ..services.assets import fetch_image_bytes
from ..stores.atlas_client import _get_session

# ===== 画布与调色板 =====
W, H = 1160, 900
C_LIGHT = (248, 249, 250)
C_STRIPE = (234, 235, 238)
C_GRID = (162, 169, 177)
C_HEAD = (220, 225, 232)
C_TEXT = (32, 33, 34)
C_SUB = (100, 108, 120)
C_WHITE = (255, 255, 255)
C_GOLD = (180, 140, 40)

# 布局: 左侧面板 LX..RX, 右侧面板 RIGHT_X..RIGHT_X2
LX, RX = 20, 782
RIGHT_X, RIGHT_W = 798, 344
RIGHT_X2 = RIGHT_X + RIGHT_W
HPAD = 12

# 指令卡映射（兼容 Atlas 字符串键和旧版整数键）
CARD_LETTER: dict[str, str] = {
    "arts": "A", "buster": "B", "quick": "Q",
    "1": "A", "2": "B", "3": "Q",
}
CARD_COLORS: dict[str, tuple] = {
    "A": ((42, 120, 210), (28, 90, 170)),
    "B": ((210, 70, 70), (170, 45, 45)),
    "Q": ((42, 160, 80), (18, 120, 55)),
}

ATTR_MAP: dict[str, str] = {
    "earth": "地", "sky": "天", "human": "人", "star": "星", "beast": "兽",
}
GENDER_MAP: dict[str, str] = {
    "male": "男性", "female": "女性", "unknown": "不明",
}
SUB_ATTR_MAP: dict[str, str] = {
    "humanoid": "人形", "servant": "从者", "undead": "不死",
    "animal": "动物", "demon": "魔性", "earth": "地属性",
    "sky": "天属性", "human": "人属性", "divine": "神性",
}
CLASS_COLORS: dict[str, tuple] = {
    "SABER": (74, 43, 34), "ARCHER": (67, 128, 194), "LANCER": (42, 160, 80),
    "RIDER": (95, 163, 229), "CASTER": (116, 56, 34), "ASSASSIN": (130, 95, 75),
    "BERSERKER": (157, 88, 41), "RULER": (234, 184, 118), "AVENGER": (52, 33, 55),
    "ALTEREGO": (220, 154, 75), "MOONCANCER": (32, 115, 187),
    "FOREIGNER": (32, 77, 152), "PRETENDER": (109, 47, 34),
    "SHIELDER": (88, 132, 181), "BEAST": (185, 115, 34),
}
CLASS_CN: dict[str, str] = {
    "SABER": "剑阶", "ARCHER": "弓阶", "LANCER": "枪阶",
    "RIDER": "骑阶", "CASTER": "术阶", "ASSASSIN": "杀阶",
    "BERSERKER": "狂阶", "RULER": "裁阶", "AVENGER": "仇阶",
    "ALTEREGO": "分身", "MOONCANCER": "月癌", "FOREIGNER": "异界",
    "PRETENDER": "伪阶", "SHIELDER": "盾阶", "BEAST": "兽阶",
}

PARAM_LABELS = ["筋力", "耐久", "敏捷", "魔力", "幸运", "宝具"]
PARAM_KEYS = ["strength", "endurance", "agility", "mana", "luck", "np"]

# cardDetails 卡型键与显示标签
HIT_TYPE_ORDER = ["quick", "arts", "buster", "extra", "weakHit", "strengthHit"]
HIT_TYPE_LABEL: dict[str, str] = {
    "quick": "Quick", "arts": "Arts", "buster": "Buster",
    "extra": "Extra", "weakHit": "弱攻", "strengthHit": "强攻",
}


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """按优先顺序尝试加载 CJK 字体；全部失败时退回 Pillow 默认位图字体。"""
    for p in [
        "plugins/fgo/data/fonts/NotoSansCJKsc-Regular.otf",
        "plugins/fgo/data/fonts/SourceHanSansSC-Regular.otf",
    ]:
        try:
            return ImageFont.truetype(p, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


_DEFAULT_FONT_SIZE = 12  # 默认位图字体的近似高度（像素）


def _fsize(font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> int:
    """字体高度（兼容 FreeType 和默认位图字体）"""
    try:
        return font.size  # type: ignore[attr-defined]
    except AttributeError:
        return _DEFAULT_FONT_SIZE


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


def _stat(level: int, base: Any, maxv: Any, lv_max: int, growth: list[int]) -> int | None:
    if level == 1:
        return int(base) if base is not None else None
    if lv_max == level and maxv is not None:
        return int(maxv)
    if growth and len(growth) >= level:
        return int(growth[level - 1])
    return None


def _fmt(v: Any) -> str:
    return "—" if v is None else str(v)


def _pct_fmt(v: Any) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.1f}%"
    except (TypeError, ValueError):
        return str(v)


def draw_flat_card(
    d: ImageDraw.ImageDraw,
    x: int, y: int, w: int, h: int,
    letter: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    """绘制扁平风格指令卡（fgowiki 表格样式，无圆角）"""
    letter = (letter or "?").upper()
    fill, border = CARD_COLORS.get(letter, ((150, 150, 150), (120, 120, 120)))
    d.rectangle((x, y, x + w, y + h), fill=fill, outline=border, width=2)
    # 顶部高光条
    lighter = tuple(min(255, c + 50) for c in fill)
    d.rectangle((x + 2, y + 2, x + w - 2, y + max(3, h // 5)), fill=lighter)
    fs = _fsize(font)
    tw = d.textlength(letter, font=font)
    d.text((x + (w - tw) / 2, y + (h - fs) / 2 - 1), letter, font=font, fill=C_WHITE)


def _stripe_bg(
    d: ImageDraw.ImageDraw, y: int, h: int, index: int,
    x1: int = LX, x2: int = RX,
) -> None:
    """交替条纹背景"""
    d.rectangle((x1, y, x2, y + h), fill=C_STRIPE if index % 2 == 1 else C_WHITE)


def _six_col_table(
    d: ImageDraw.ImageDraw,
    x1: int, y: int, x2: int,
    labels: list[str], values: list[str],
    hdr_h: int, val_h: int,
    f_hdr: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    f_val: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    """绘制6列均分的表头+数值行（用于属性表和能力值表）"""
    n = len(labels)
    total_h = hdr_h + val_h
    col_w = (x2 - x1) // n
    d.rectangle((x1, y, x2, y + total_h), fill=C_WHITE, outline=C_GRID, width=1)
    for i in range(n):
        cx1 = x1 + i * col_w
        cx2 = x1 + (i + 1) * col_w
        if i > 0:
            d.line((cx1, y, cx1, y + total_h), fill=C_GRID, width=1)
        d.rectangle((cx1, y, cx2, y + hdr_h), fill=C_HEAD)
        # 表头居中
        tw = d.textlength(labels[i], font=f_hdr)
        d.text(
            (cx1 + (col_w - tw) / 2, y + (hdr_h - _fsize(f_hdr)) / 2),
            labels[i], font=f_hdr, fill=C_SUB,
        )
        # 数值居中
        tw = d.textlength(values[i], font=f_val)
        d.text(
            (cx1 + (col_w - tw) / 2, y + hdr_h + (val_h - _fsize(f_val)) / 2),
            values[i], font=f_val, fill=C_TEXT,
        )


async def render_svt_base_table(detail: dict[str, Any]) -> bytes:
    img = Image.new("RGBA", (W, H), C_LIGHT)
    d = ImageDraw.Draw(img)

    # 字体集
    f_lg = _font(25)   # 从者名（大）
    f_md = _font(18)   # 中号（No.等）
    f_nm = _font(15)   # 正文
    f_sm = _font(13)   # 小正文
    f_xs = _font(11)   # 极小标签
    f_card = _font(19) # 指令卡字母

    # ── 数据提取 ─────────────────────────────────────────────────────────
    name = str(detail.get("name") or "")
    name_jp = str(detail.get("originalName") or detail.get("ruby") or "")
    cno = int(detail.get("collectionNo") or 0)
    rarity = int(detail.get("rarity") or 0)
    cost = int(detail.get("cost") or 0)
    cls = str(detail.get("className") or "").upper()
    cls_cn = CLASS_CN.get(cls, cls)
    cls_color = CLASS_COLORS.get(cls, (100, 100, 100))
    attr = ATTR_MAP.get(str(detail.get("attribute") or ""), str(detail.get("attribute") or ""))
    sub_attr = SUB_ATTR_MAP.get(str(detail.get("subAttribute") or ""), str(detail.get("subAttribute") or "") or "—")
    gender = GENDER_MAP.get(str(detail.get("gender") or ""), str(detail.get("gender") or "") or "—")

    profile = detail.get("profile") or {}
    illustrator = str(profile.get("illustrator") or "—")
    cv = str(profile.get("cv") or "—")
    param_stats: dict = profile.get("stats") or {}

    atk_base = detail.get("atkBase")
    atk_max = detail.get("atkMax")
    hp_base = detail.get("hpBase")
    hp_max = detail.get("hpMax")
    lv_max = int(detail.get("lvMax") or 80)
    atk_g: list = detail.get("atkGrowth") or []
    hp_g: list = detail.get("hpGrowth") or []

    cards_raw = detail.get("cards") or []
    letters = [CARD_LETTER.get(str(x), "?") for x in cards_raw][:5]

    star_absorb = detail.get("starAbsorb")
    star_gen = detail.get("starGen")
    death_rate = detail.get("instantDeathChance")
    np_charge_atk = detail.get("npChargeAtk")
    np_charge_def = detail.get("npChargeDef")

    card_details: dict = detail.get("cardDetails") or {}

    traits_list = detail.get("traits") or []
    trait_names = [
        str(t.get("name") or t.get("id") or "")
        for t in traits_list
        if isinstance(t, dict)
    ]
    trait_names = [n for n in trait_names if n]

    # ====================================================================
    # 左侧面板
    # ====================================================================
    cur_y = 8

    # ── 1. 名称块 ────────────────────────────────────────────────────────
    name_h = 72
    d.rectangle((LX, cur_y, RX, cur_y + name_h), fill=C_WHITE, outline=C_GRID, width=1)
    # 职阶色条
    d.rectangle((LX + 1, cur_y + 1, LX + 7, cur_y + name_h - 1), fill=cls_color)
    # 职阶徽章
    badge_x = LX + 14
    badge_w, badge_h = 44, 44
    badge_y = cur_y + (name_h - badge_h) // 2
    d.rectangle((badge_x, badge_y, badge_x + badge_w, badge_y + badge_h), fill=cls_color)
    badge_class_label = cls_cn if cls_cn else cls[:3]
    tw = d.textlength(badge_class_label, font=f_xs)
    d.text(
        (badge_x + (badge_w - tw) / 2, badge_y + (badge_h - _fsize(f_xs)) / 2),
        badge_class_label, font=f_xs, fill=C_WHITE,
    )
    # 从者名
    nx = badge_x + badge_w + 12
    d.text((nx, cur_y + 10), name, font=f_lg, fill=C_TEXT)
    if name_jp and name_jp != name:
        d.text((nx, cur_y + 46), name_jp, font=f_xs, fill=C_SUB)
    # 星级（右对齐）
    stars_str = "★" * rarity
    tw = d.textlength(stars_str, font=_font(15))
    d.text((RX - tw - 14, cur_y + 12), stars_str, font=_font(15), fill=C_GOLD)

    cur_y += name_h + 4

    # ── 2. 画师 / 配音行 ──────────────────────────────────────────────────
    ic_h = 30
    col_mid = LX + (RX - LX) // 2
    d.rectangle((LX, cur_y, RX, cur_y + ic_h), fill=C_WHITE, outline=C_GRID, width=1)
    d.line((col_mid, cur_y, col_mid, cur_y + ic_h), fill=C_GRID, width=1)
    # 左：画师
    d.rectangle((LX, cur_y, LX + 66, cur_y + ic_h), fill=C_HEAD)
    d.text((LX + 6, cur_y + (ic_h - _fsize(f_xs)) // 2), "画师", font=f_xs, fill=C_SUB)
    d.text((LX + 74, cur_y + (ic_h - _fsize(f_sm)) // 2), illustrator, font=f_sm, fill=C_TEXT)
    # 右：配音
    d.rectangle((col_mid, cur_y, col_mid + 58, cur_y + ic_h), fill=C_HEAD)
    d.text((col_mid + 6, cur_y + (ic_h - _fsize(f_xs)) // 2), "配音", font=f_xs, fill=C_SUB)
    d.text((col_mid + 66, cur_y + (ic_h - _fsize(f_sm)) // 2), cv, font=f_sm, fill=C_TEXT)

    cur_y += ic_h + 4

    # ── 3. 基础属性表（6列：COST / 稀有度 / 职阶 / 属性 / 副属性 / 性别）────
    attr_labels = ["COST", "稀有度", "职阶", "属性", "副属性", "性别"]
    attr_vals = [str(cost), f"★{rarity}", cls_cn or cls, attr, sub_attr, gender]
    _six_col_table(d, LX, cur_y, RX, attr_labels, attr_vals, 20, 28, f_xs, f_sm)
    cur_y += 20 + 28 + 4  # hdr_h + val_h + spacing

    # ── 4. 能力值表（6列：筋力 / 耐久 / 敏捷 / 魔力 / 幸运 / 宝具）─────────
    param_vals = [str(param_stats.get(k) or "—") for k in PARAM_KEYS]
    _six_col_table(d, LX, cur_y, RX, PARAM_LABELS, param_vals, 20, 28, f_xs, f_sm)
    cur_y += 20 + 28 + 4  # hdr_h + val_h + spacing

    # ── 5. ATK / HP 数值表 ────────────────────────────────────────────────
    # 第三列用 "Lv.max" 避免与后续固定等级列标签重复
    stat_hdrs = ["", "Lv.1", "Lv.max", "Lv.90", "Lv.100", "Lv.120"]
    # 列宽比例：标签列较窄，数值列等宽
    raw_widths = [68, 118, 118, 118, 118, 118]
    raw_total = sum(raw_widths)
    panel_w = RX - LX
    stat_col_x = [LX]
    acc = 0
    for rw in raw_widths:
        acc += rw
        stat_col_x.append(LX + int(acc * panel_w / raw_total))
    stat_col_x[-1] = RX  # 精确对齐右边界

    stat_hdr_h, stat_row_h = 24, 28
    # 表头
    d.rectangle((LX, cur_y, RX, cur_y + stat_hdr_h), fill=C_HEAD, outline=C_GRID, width=1)
    for i, hdr in enumerate(stat_hdrs):
        x1, x2 = stat_col_x[i], stat_col_x[i + 1]
        if i > 0:
            d.line((x1, cur_y, x1, cur_y + stat_hdr_h), fill=C_GRID, width=1)
        if hdr:
            tw = d.textlength(hdr, font=f_xs)
            d.text(
                (x1 + (x2 - x1 - tw) / 2, cur_y + (stat_hdr_h - _fsize(f_xs)) / 2),
                hdr, font=f_xs, fill=C_SUB,
            )

    stat_data_y = cur_y + stat_hdr_h
    atk_vals = [
        _stat(1, atk_base, atk_max, lv_max, atk_g),
        _stat(lv_max, atk_base, atk_max, lv_max, atk_g),
        _stat(90, atk_base, atk_max, lv_max, atk_g),
        _stat(100, atk_base, atk_max, lv_max, atk_g),
        _stat(120, atk_base, atk_max, lv_max, atk_g),
    ]
    hp_vals = [
        _stat(1, hp_base, hp_max, lv_max, hp_g),
        _stat(lv_max, hp_base, hp_max, lv_max, hp_g),
        _stat(90, hp_base, hp_max, lv_max, hp_g),
        _stat(100, hp_base, hp_max, lv_max, hp_g),
        _stat(120, hp_base, hp_max, lv_max, hp_g),
    ]

    for ri, (row_label, vals) in enumerate([("ATK", atk_vals), ("HP", hp_vals)]):
        ry = stat_data_y + ri * stat_row_h
        _stripe_bg(d, ry, stat_row_h, ri)
        d.line((LX, ry, RX, ry), fill=C_GRID, width=1)
        d.text((LX + 8, ry + (stat_row_h - _fsize(f_nm)) // 2), row_label, font=f_nm, fill=C_TEXT)
        for ci, v in enumerate(vals):
            x1, x2 = stat_col_x[ci + 1], stat_col_x[ci + 2]
            sv = _fmt(v)
            tw = d.textlength(sv, font=f_nm)
            d.text((x1 + (x2 - x1 - tw) / 2, ry + (stat_row_h - _fsize(f_nm)) // 2), sv, font=f_nm, fill=C_TEXT)

    # 纵线 & 下边框
    bottom_stat = stat_data_y + 2 * stat_row_h
    for xi in stat_col_x[1:]:
        d.line((xi, cur_y, xi, bottom_stat), fill=C_GRID, width=1)
    d.line((LX, bottom_stat, RX, bottom_stat), fill=C_GRID, width=1)
    d.rectangle((LX, cur_y, RX, bottom_stat), outline=C_GRID, width=1)

    cur_y = bottom_stat + 4

    # ── 6. 指令卡配置行 ───────────────────────────────────────────────────
    sec_hdr_h = 22
    d.rectangle((LX, cur_y, RX, cur_y + sec_hdr_h), fill=C_HEAD, outline=C_GRID, width=1)
    d.text((LX + 8, cur_y + (sec_hdr_h - _fsize(f_xs)) // 2), "指令卡配置", font=f_xs, fill=C_SUB)
    cur_y += sec_hdr_h

    cw_c, ch_c = 54, 58
    c_gap = 6
    cx0 = LX + 10
    c_row_y = cur_y + 4
    for i, lt in enumerate(letters):
        draw_flat_card(d, cx0 + i * (cw_c + c_gap), c_row_y, cw_c, ch_c, lt, f_card)
    cur_y += ch_c + 8 + 4

    # ── 7. Hit 分布表 ──────────────────────────────────────────────────────
    hit_rows: list[tuple[str, int, list]] = []
    if isinstance(card_details, dict):
        for key in HIT_TYPE_ORDER:
            cd = card_details.get(key)
            if cd and isinstance(cd, dict):
                hits = cd.get("hitsDistribution") or []
                if hits and isinstance(hits, list):
                    hit_rows.append((HIT_TYPE_LABEL.get(key, key), len(hits), hits))

    if hit_rows:
        hit_hdr_h, hit_row_h = 20, 24
        hcol_xs = [LX, LX + 68, LX + 112, RX]
        hit_hdrs = ["卡型", "Hit数", "百分比分布"]

        d.rectangle((LX, cur_y, RX, cur_y + hit_hdr_h), fill=C_HEAD, outline=C_GRID, width=1)
        for hi, hdr in enumerate(hit_hdrs):
            x1, x2 = hcol_xs[hi], hcol_xs[hi + 1]
            if hi > 0:
                d.line((x1, cur_y, x1, cur_y + hit_hdr_h), fill=C_GRID, width=1)
            tw = d.textlength(hdr, font=f_xs)
            d.text(
                (x1 + (x2 - x1 - tw) / 2, cur_y + (hit_hdr_h - _fsize(f_xs)) // 2),
                hdr, font=f_xs, fill=C_SUB,
            )

        for ri, (label, nhits, dist) in enumerate(hit_rows):
            row_y = cur_y + hit_hdr_h + ri * hit_row_h
            _stripe_bg(d, row_y, hit_row_h, ri)
            d.line((LX, row_y, RX, row_y), fill=C_GRID, width=1)
            for xi in hcol_xs:
                d.line((xi, row_y, xi, row_y + hit_row_h), fill=C_GRID, width=1)
            d.text((hcol_xs[0] + 6, row_y + (hit_row_h - _fsize(f_sm)) // 2), label, font=f_sm, fill=C_TEXT)
            nh_s = str(nhits)
            tw = d.textlength(nh_s, font=f_sm)
            d.text(
                (hcol_xs[1] + (hcol_xs[2] - hcol_xs[1] - tw) / 2, row_y + (hit_row_h - _fsize(f_sm)) // 2),
                nh_s, font=f_sm, fill=C_TEXT,
            )
            dist_s = " ".join(f"{v}%" for v in dist)
            d.text((hcol_xs[2] + 4, row_y + (hit_row_h - _fsize(f_xs)) // 2), dist_s, font=f_xs, fill=C_SUB)

        hit_bottom = cur_y + hit_hdr_h + len(hit_rows) * hit_row_h
        d.line((LX, hit_bottom, RX, hit_bottom), fill=C_GRID, width=1)
        cur_y = hit_bottom + 4

    # ── 8. 杂项数值（即死 / 集星权重 / 出星率 / NP获得）─────────────────────
    misc_labels = ["即死率", "集星权重", "出星率", "NP获得(攻)", "NP获得(受)"]
    misc_vals = [
        _pct_fmt(death_rate),
        _fmt(star_absorb),
        _pct_fmt(star_gen),
        _pct_fmt(np_charge_atk),
        _pct_fmt(np_charge_def),
    ]
    _six_col_table(
        d, LX, cur_y, RX,
        misc_labels, misc_vals,
        20, 26, f_xs, f_sm,
    )
    cur_y += 20 + 26 + 4  # hdr_h + val_h + spacing

    # ── 9. 特性标签 ───────────────────────────────────────────────────────
    if trait_names:
        trait_hdr_h, trait_body_h = 22, 36
        d.rectangle((LX, cur_y, RX, cur_y + trait_hdr_h + trait_body_h), fill=C_WHITE, outline=C_GRID, width=1)
        d.rectangle((LX, cur_y, LX + 56, cur_y + trait_hdr_h), fill=C_HEAD)
        d.text((LX + 6, cur_y + (trait_hdr_h - _fsize(f_xs)) // 2), "特性", font=f_xs, fill=C_SUB)
        trait_text = "  /  ".join(trait_names[:18])
        if len(trait_names) > 18:
            trait_text += "  ..."
        d.text(
            (LX + 6, cur_y + trait_hdr_h + (trait_body_h - _fsize(f_xs)) // 2),
            trait_text, font=f_xs, fill=C_SUB,
        )
        cur_y += trait_hdr_h + trait_body_h + 4

    # ====================================================================
    # 右侧面板
    # ====================================================================
    rp_x1, rp_x2 = RIGHT_X, RIGHT_X2
    rp_y1 = 8
    rp_y2 = H - 26
    rp_pad = 12

    d.rectangle((rp_x1, rp_y1, rp_x2, rp_y2), fill=C_WHITE, outline=C_GRID, width=1)

    ry = rp_y1 + rp_pad
    rx_r = rp_x1 + rp_pad
    panel_inner_w = rp_x2 - rp_x1 - 2 * rp_pad

    # No. 和星级
    d.text((rx_r, ry), f"No.{cno:03d}", font=f_md, fill=C_TEXT)
    stars_s = "★" * rarity
    tw = d.textlength(stars_s, font=_font(14))
    d.text((rp_x2 - tw - rp_pad, ry + 3), stars_s, font=_font(14), fill=C_GOLD)
    ry += 28

    # 职阶徽章
    b2_w, b2_h = 52, 22
    d.rectangle((rx_r, ry, rx_r + b2_w, ry + b2_h), fill=cls_color)
    badge_label = cls_cn or cls
    tw = d.textlength(badge_label, font=f_xs)
    d.text((rx_r + (b2_w - tw) / 2, ry + (b2_h - _fsize(f_xs)) / 2), badge_label, font=f_xs, fill=C_WHITE)
    ry += b2_h + 8

    # 立绘区域
    art_x1 = rx_r
    art_y1 = ry
    art_w = panel_inner_w
    art_h = min(400, rp_y2 - ry - 120)
    art_x2 = art_x1 + art_w
    art_y2 = art_y1 + art_h
    d.rectangle((art_x1, art_y1, art_x2, art_y2), fill=(240, 243, 248), outline=C_GRID, width=1)

    # 获取并绘制立绘
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

    ry = art_y2 + 8

    # 阶段选择器（静态 UI）
    stg_count = 4
    stg_h = 26
    stg_gap = 3
    stg_w = (panel_inner_w - (stg_count - 1) * stg_gap) // stg_count
    for si in range(stg_count):
        sx = rx_r + si * (stg_w + stg_gap)
        is_active = si == 3
        d.rectangle((sx, ry, sx + stg_w, ry + stg_h), fill=cls_color if is_active else C_STRIPE, outline=C_GRID, width=1)
        stg_lbl = f"段{si + 1}"
        tw = d.textlength(stg_lbl, font=f_xs)
        d.text(
            (sx + (stg_w - tw) / 2, ry + (stg_h - _fsize(f_xs)) / 2),
            stg_lbl, font=f_xs, fill=C_WHITE if is_active else C_SUB,
        )
    ry += stg_h + 6

    # 底部指令卡（小）
    if letters:
        bc_w, bc_h = 44, 46
        bc_gap = 4
        bc_total = len(letters) * bc_w + (len(letters) - 1) * bc_gap
        bc_x0 = rx_r + (panel_inner_w - bc_total) // 2
        for i, lt in enumerate(letters):
            draw_flat_card(d, bc_x0 + i * (bc_w + bc_gap), ry, bc_w, bc_h, lt, _font(15))
        ry += bc_h + 6

    # 名称条
    nstrip_h = 32
    if ry + nstrip_h <= rp_y2 - 2:
        d.rectangle((rp_x1 + 1, ry, rp_x2 - 1, ry + nstrip_h), fill=C_HEAD)
        tw = d.textlength(name, font=f_nm)
        d.text(
            (rp_x1 + 1 + (rp_x2 - rp_x1 - 2 - tw) / 2, ry + (nstrip_h - _fsize(f_nm)) // 2),
            name, font=f_nm, fill=C_TEXT,
        )

    # ====================================================================
    # 页脚
    # ====================================================================
    footer = "数据来源：Atlas Academy / Mooncell  |  fgo.wiki"
    ff = _font(11)
    tw = d.textlength(footer, font=ff)
    d.text(((W - tw) / 2, H - 18), footer, font=ff, fill=C_SUB)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
