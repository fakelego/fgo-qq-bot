# plugins/fgo/render/svt_mooncell.py
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from ..services.assets import fetch_image_bytes
from ..stores.atlas_client import _get_session

W, H = 1600, 1150
BASE_W, BASE_H = 1200, 900
S = W / BASE_W  # 1.333...
BG = (245, 247, 250, 255)
GRID = (170, 176, 186, 255)
HEAD = (236, 239, 244, 255)
TEXT = (30, 33, 40, 255)
SUB = (60, 66, 76, 255)

CARD_MAP = {"1": "Arts", "2": "Buster", "3": "Quick"}
CARD_LETTER = {"1": "A", "2": "B", "3": "Q"}

ATTR_MAP = {"earth": "地", "sky": "天", "human": "人", "star": "星", "beast": "兽"}


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
    """等比缩放并裁剪，填满整个框（Mooncell 风格）"""
    im = im.convert("RGBA")
    iw, ih = im.size
    if iw == 0 or ih == 0:
        return Image.new("RGBA", (box_w, box_h), (255, 255, 255, 255))

    scale = max(box_w / iw, box_h / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    resized = im.resize((nw, nh), Image.Resampling.LANCZOS)

    x0 = (nw - box_w) // 2
    y0 = (nh - box_h) // 2
    return resized.crop((x0, y0, x0 + box_w, y0 + box_h))


def draw_cmd_card(d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, letter: str, font: ImageFont.ImageFont):
    """方案2：纯绘制指令卡图标（Q/A/B）"""
    letter = (letter or "?").upper()
    colors = {
        "Q": ((42, 160, 80, 255), (18, 120, 55, 255)),
        "A": ((42, 120, 210, 255), (28, 90, 170, 255)),
        "B": ((210, 70, 70, 255), (170, 45, 45, 255)),
        "?": ((150, 150, 150, 255), (120, 120, 120, 255)),
    }
    fill, border = colors.get(letter, colors["?"])
    r = max(8, min(w, h) // 6)

    d.rounded_rectangle((x, y, x + w, y + h), radius=r, fill=fill, outline=border, width=3)
    d.rounded_rectangle((x + 4, y + 4, x + w - 4, y + h // 3), radius=r - 3, fill=(255, 255, 255, 40))

    tw = d.textlength(letter, font=font)
    d.text((x + (w - tw) / 2, y + (h - font.size) / 2 - 2), letter, font=font, fill=(255, 255, 255, 235))
def _stat_at_level(base: int | None, maxv: int | None, lv_max: int | None, growth: list[int] | None, level: int):
    if level == 1:
        return base
    if lv_max == level and maxv is not None:
        return int(maxv)
    if growth and len(growth) >= level:
        return int(growth[level - 1])
    return None


async def render_svt_base_table(detail: dict[str, Any]) -> bytes:
    """
    Mooncell 风格：基础数值 + 立绘 + 指令卡（第一版核心）
    """
    
    img = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(img)

    def sc(x: int) -> int:
        return int(x * S)

    f_title = _font(44)
    f_mid = _font(26)
    f_small = _font(20)
    f_num = _font(22)

    name = str(detail.get("name") or "")
    cno = int(detail.get("collectionNo") or 0)
    rarity = int(detail.get("rarity") or 0)
    cost = int(detail.get("cost") or 0)
    class_name = str(detail.get("className") or "").upper()
    attribute = ATTR_MAP.get(str(detail.get("attribute") or ""), str(detail.get("attribute") or ""))

    atk_base = detail.get("atkBase")
    atk_max = detail.get("atkMax")
    hp_base = detail.get("hpBase")
    hp_max = detail.get("hpMax")
    lv_max = detail.get("lvMax")
    atk_g = detail.get("atkGrowth") or []
    hp_g = detail.get("hpGrowth") or []

    atk_1 = _stat_at_level(atk_base, atk_max, lv_max, atk_g, 1)
    atk_90 = _stat_at_level(atk_base, atk_max, lv_max, atk_g, 90)
    atk_100 = _stat_at_level(atk_base, atk_max, lv_max, atk_g, 100)
    atk_120 = _stat_at_level(atk_base, atk_max, lv_max, atk_g, 120)

    hp_1 = _stat_at_level(hp_base, hp_max, lv_max, hp_g, 1)
    hp_90 = _stat_at_level(hp_base, hp_max, lv_max, hp_g, 90)
    hp_100 = _stat_at_level(hp_base, hp_max, lv_max, hp_g, 100)
    hp_120 = _stat_at_level(hp_base, hp_max, lv_max, hp_g, 120)

    # ===== 标题 =====
    d.text((40, 18), "基础数值", font=f_title, fill=TEXT)
    d.line((40, 78, W - 40, 78), fill=GRID, width=3)

    # ===== 左侧表格区域 =====
    left_x1, left_y1 = 40, 110
    left_x2, left_y2 = 980, 900
    d.rectangle((left_x1, left_y1, left_x2, left_y2), outline=GRID, width=sc(2), fill=(255, 255, 255, 255))

    # 顶部姓名栏
    d.rectangle((left_x1, left_y1, left_x2, left_y1 + 56), fill=HEAD, outline=GRID, width=sc(2))
    d.text((left_x1 + 16, left_y1 + 12), name, font=f_mid, fill=TEXT)

    # 基础信息小表（仿 Mooncell：COST/稀有度/职阶/属性）
    base_rows_y = left_y1 + 56
    row_h = 52
    col_w = (left_x2 - left_x1) // 4
    labels = ["COST", "稀有度", "职阶", "属性"]
    values = [str(cost), f"★{rarity}", class_name, attribute]
    for i in range(4):
        x1 = left_x1 + i * col_w
        x2 = x1 + col_w
        # label row
        d.rectangle((x1, base_rows_y, x2, base_rows_y + 28), fill=HEAD, outline=GRID, width=sc(2))
        # value row
        d.rectangle((x1, base_rows_y + 28, x2, base_rows_y + row_h), fill=(255, 255, 255, 255), outline=GRID, width=sc(2))
        d.text((x1 + 10, base_rows_y + 4), labels[i], font=f_small, fill=SUB)
        d.text((x1 + 10, base_rows_y + 32), values[i], font=f_num, fill=TEXT)

    # ATK/HP 表格（基础/90/100/120）
    stats_y1 = base_rows_y + row_h
    stats_y2 = stats_y1 + 220
    d.rectangle((left_x1, stats_y1, left_x2, stats_y2), outline=GRID, width=sc(2), fill=(255, 255, 255, 255))

    headers = ["", "基础", "90级", "100级", "120级"]
    cols = [100, 150, 150, 150, 150]
    # x positions
    xs = [left_x1]
    for w0 in cols:
        xs.append(xs[-1] + w0)
    # normalize to fit
    scale = (left_x2 - left_x1) / (xs[-1] - left_x1)
    xs = [int(left_x1 + (x - left_x1) * scale) for x in xs]

    # header row
    d.rectangle((left_x1, stats_y1, left_x2, stats_y1 + 42), fill=HEAD, outline=GRID, width=sc(2))
    for i, htxt in enumerate(headers):
        x1, x2 = xs[i], xs[i + 1]
        d.line((x1, stats_y1, x1, stats_y2), fill=GRID, width=sc(2))
        tw = d.textlength(htxt, font=f_small)
        d.text((x1 + (x2 - x1 - tw) / 2, stats_y1 + 10), htxt, font=f_small, fill=SUB)
    d.line((left_x2, stats_y1, left_x2, stats_y2), fill=GRID, width=sc(2))

    def fmt(v):
        return "—" if v is None else str(v)

    # rows
    row1 = stats_y1 + 42
    row2 = row1 + 84
    row3 = row2 + 84
    for yy in (row1, row2, row3, stats_y2):
        d.line((left_x1, yy, left_x2, yy), fill=GRID, width=sc(2))

    # ATK row
    d.text((left_x1 + 20, row1 + 28), "ATK", font=f_num, fill=TEXT)
    atk_vals = [fmt(atk_1), fmt(atk_90), fmt(atk_100), fmt(atk_120)]
    for i, v in enumerate(atk_vals, start=1):
        x1, x2 = xs[i], xs[i + 1]
        tw = d.textlength(v, font=f_num)
        d.text((x1 + (x2 - x1 - tw) / 2, row1 + 28), v, font=f_num, fill=TEXT)

    # HP row
    d.text((left_x1 + 20, row2 + 28), "HP", font=f_num, fill=TEXT)
    hp_vals = [fmt(hp_1), fmt(hp_90), fmt(hp_100), fmt(hp_120)]
    for i, v in enumerate(hp_vals, start=1):
        x1, x2 = xs[i], xs[i + 1]
        tw = d.textlength(v, font=f_num)
        d.text((x1 + (x2 - x1 - tw) / 2, row2 + 28), v, font=f_num, fill=TEXT)

    # 指令卡：Mooncell 风格（方案2：纯绘制）
    cards_y = stats_y2
    d.rectangle((left_x1, cards_y, left_x2, left_y2), outline=GRID, width=3, fill=(255, 255, 255, 255))
    d.rectangle((left_x1, cards_y, left_x1 + 120, left_y2), fill=HEAD, outline=GRID, width=3)
    d.text((left_x1 + 20, cards_y + 22), "指令卡", font=f_small, fill=SUB)

    cards = detail.get("cards") or []  # ['3','1','1','2','2']
    letters = [CARD_LETTER.get(str(x), "?") for x in cards][:5]

    card_font = _font(34)
    card_w, card_h = 96, 96
    gap = 14
    start_x = left_x1 + 160
    start_y = cards_y + 18

    for i, lt in enumerate(letters):
        x = start_x + i * (card_w + gap)
        draw_cmd_card(d, x, start_y, card_w, card_h, lt, card_font)

    # ===== 右侧：编号 + 星级 + 立绘 =====
    # ===== 右侧：编号 + 星级 + 立绘（Mooncell 风格）=====
    right_x1, right_y1 = 1020, 110
    right_x2, right_y2 = W - 40, 1060
    d.rectangle((right_x1, right_y1, right_x2, right_y2), outline=GRID, width=2, fill=(255, 255, 255, 255))

    # 顶部信息条
    top_h = 140
    d.rectangle((right_x1, right_y1, right_x2, right_y1 + top_h), fill=HEAD, outline=GRID, width=2)

    d.text((right_x1 + 20, right_y1 + 18), f"No.{cno}", font=_font(28), fill=TEXT)
    d.text((right_x1 + 20, right_y1 + 62), "★" * rarity, font=_font(24), fill=(180, 140, 40, 255))

    # 立绘框：固定边距，尽量接近 Mooncell 的“填满大图块”
    art_pad = 18
    art_x1 = right_x1 + art_pad
    art_y1 = right_y1 + top_h + art_pad
    art_x2 = right_x2 - art_pad
    art_y2 = right_y2 - art_pad

    # 给底部 footer/未来控件预留一点（现在先留 40px）
    art_y2 -= 40

    # 立绘背景框（可选）
    d.rectangle((art_x1, art_y1, art_x2, art_y2), outline=GRID, width=2, fill=(255, 255, 255, 255))

    cg = (extra.get("charaGraph") or {}).get("ascension") or {}
    cg_url = cg.get("4") or cg.get("3") or cg.get("2") or cg.get("1")
    if cg_url:
        b = await fetch_image_bytes(sess, cg_url)
        art = Image.open(BytesIO(b)).convert("RGBA")
        bw = art_x2 - art_x1 - 4
        bh = art_y2 - art_y1 - 4
        art = fit_cover(art, bw, bh)  # 关键：cover 填满裁剪，不留白
        img.paste(art, (art_x1 + 2, art_y1 + 2), art)

        buf = BytesIO()
        # ===== footer：信息来源（简版）=====
        footer = "来源：Atlas Academy / Mooncell"
        ff = _font(18)  # 如果你做了缩放系数 S，就用 _font(int(18 * S))
        tw = d.textlength(footer, font=ff)
        d.text(((W - tw) / 2, H - 34), footer, font=ff, fill=(110, 116, 128, 255))

        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    img.save(buf, format="PNG")
    return buf.getvalue()