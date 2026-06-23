# plugins/fgo/render/svt_card.py
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw, ImageFont

CARD_W, CARD_H = 960, 340

CARD_MAP = {"1": "A", "2": "B", "3": "Q"}  # Atlas: 1=Arts 2=Buster 3=Quick

ATTR_MAP = {
    "earth": "地",
    "sky": "天",
    "human": "人",
    "star": "星",
    "beast": "兽",
}

def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    # 尽量用项目内字体；没有就退回默认
    # 你后面建议放一个：plugins/fgo/data/fonts/NotoSansCJKsc-Regular.otf
    for p in [
        "plugins/fgo/data/fonts/NotoSansCJKsc-Regular.otf",
        "plugins/fgo/data/fonts/SourceHanSansSC-Regular.otf",
    ]:
        try:
            return ImageFont.truetype(p, size=size)
        except Exception:
            pass
    return ImageFont.load_default()

@dataclass
class MiniSvt:
    name: str
    rarity: int
    collection_no: int
    atlas_id: int
    class_name: str
    cost: int
    attribute: str
    cards: str  # like "QAABB"
    face_bytes: bytes | None
    atk: dict[str, int | None]  # keys: base/90/100/120
    hp: dict[str, int | None]

def _pick_face_url(svt: dict[str, Any], prefer_asc: str = "4") -> str | None:
    extra = svt.get("extraAssets") or {}
    faces = (extra.get("faces") or {}).get("ascension") or {}
    # ascension keys are strings "1".."4"
    return faces.get(prefer_asc) or faces.get("1")

def _cards_to_str(cards: list[str] | None) -> str:
    if not cards:
        return ""
    return "".join(CARD_MAP.get(str(x), "?") for x in cards)

def _stat_at_level(
    base: int | None,
    maxv: int | None,
    lv_max: int | None,
    growth: list[int] | None,
    level: int,
) -> int | None:
    if level == 1:
        return base
    if lv_max == level and maxv is not None:
        return int(maxv)
    if growth and len(growth) >= level:
        return int(growth[level - 1])
    return None

def extract_mini(svt: dict[str, Any]) -> MiniSvt:
    name = svt.get("name") or svt.get("originalName") or "Unknown"
    rarity = int(svt.get("rarity") or 0)
    cno = int(svt.get("collectionNo") or 0)
    atlas_id = int(svt.get("id") or 0)
    class_name = str(svt.get("className") or "")
    cost = int(svt.get("cost") or 0)
    attribute_raw = str(svt.get("attribute") or "")
    attribute = ATTR_MAP.get(attribute_raw, attribute_raw)

    cards = _cards_to_str(svt.get("cards"))

    atk_base = svt.get("atkBase")
    atk_max = svt.get("atkMax")
    hp_base = svt.get("hpBase")
    hp_max = svt.get("hpMax")
    lv_max = svt.get("lvMax")

    atk_growth = svt.get("atkGrowth") or []
    hp_growth = svt.get("hpGrowth") or []

    atk = {
        "base": _stat_at_level(atk_base, atk_max, lv_max, atk_growth, 1),
        "90": _stat_at_level(atk_base, atk_max, lv_max, atk_growth, 90),
        "100": _stat_at_level(atk_base, atk_max, lv_max, atk_growth, 100),
        "120": _stat_at_level(atk_base, atk_max, lv_max, atk_growth, 120),
    }
    hp = {
        "base": _stat_at_level(hp_base, hp_max, lv_max, hp_growth, 1),
        "90": _stat_at_level(hp_base, hp_max, lv_max, hp_growth, 90),
        "100": _stat_at_level(hp_base, hp_max, lv_max, hp_growth, 100),
        "120": _stat_at_level(hp_base, hp_max, lv_max, hp_growth, 120),
    }

    return MiniSvt(
        name=name,
        rarity=rarity,
        collection_no=cno,
        atlas_id=atlas_id,
        class_name=class_name,
        cost=cost,
        attribute=attribute,
        cards=cards,
        face_bytes=None,  # 外部填充
        atk=atk,
        hp=hp,
    )

def render_mini_card(m: MiniSvt) -> bytes:
    from io import BytesIO

    W, H = CARD_W, CARD_H
    bg = (246, 248, 251, 255)        # Mooncell 风格浅灰底
    border = (180, 186, 196, 255)    # 边框灰
    grid = (195, 202, 212, 255)      # 表格线
    head_bg = (236, 239, 244, 255)   # 表头底色
    text = (25, 28, 35, 255)
    subtext = (65, 72, 85, 255)

    img = Image.new("RGBA", (W, H), bg)
    d = ImageDraw.Draw(img)

    f_title = _font(28)
    f_sub = _font(18)
    f_small = _font(16)
    f_num = _font(18)

    pad = 14
    outer = (pad, pad, W - pad, H - pad)

    # 外框圆角
    d.rounded_rectangle(outer, radius=22, outline=border, width=2, fill=bg)

    # 左侧头像区域（仿 Mooncell “图片区块”）
    left_x1 = pad + 12
    left_y1 = pad + 12
    left_x2 = left_x1 + 240
    left_y2 = H - pad - 12

    # 头像框
    face_box = (left_x1, left_y1, left_x2, left_y1 + 240)
    d.rounded_rectangle(face_box, radius=18, fill=head_bg, outline=grid, width=2)

    # 贴头像
    if m.face_bytes:
        face = Image.open(BytesIO(m.face_bytes)).convert("RGBA")
        face = face.resize((220, 220))
        img.paste(face, (left_x1 + 10, left_y1 + 10), face)

    # 右侧信息区框
    right_x1 = left_x2 + 14
    right_y1 = left_y1
    right_x2 = W - pad - 12
    right_y2 = left_y2

    # 信息区（上半）+ 表格区（下半）
    info_h = 128
    info_box = (right_x1, right_y1, right_x2, right_y1 + info_h)
    table_box = (right_x1, right_y1 + info_h + 10, right_x2, right_y2)

    d.rounded_rectangle(info_box, radius=16, fill=(255, 255, 255, 255), outline=grid, width=2)
    d.rounded_rectangle(table_box, radius=16, fill=(255, 255, 255, 255), outline=grid, width=2)

    # ===== 信息区内容（按行排版）=====
    x = right_x1 + 14
    y = right_y1 + 10

    d.text((x, y), m.name, font=f_title, fill=text)
    y += 36

    stars = "★" * max(0, m.rarity)
    d.text((x, y), f"{stars}  No.{m.collection_no}  atlas:{m.atlas_id}", font=f_sub, fill=subtext)
    y += 24

    d.text((x, y), f"{m.class_name.upper()}  COST {m.cost}  属性 {m.attribute}", font=f_sub, fill=subtext)
    y += 24

    d.text((x, y), f"配卡  {m.cards}", font=f_sub, fill=text)

    # ===== 表格绘制（Mooncell 风格网格）=====
    tx1, ty1, tx2, ty2 = table_box
    # 内边距
    tx1 += 12
    ty1 += 12
    tx2 -= 12
    ty2 -= 12

    # 表格区域：5 列（左标签 + 4 个等级），3 行（表头 + ATK + HP）
    total_w = tx2 - tx1
    total_h = ty2 - ty1

    col0 = 90  # ATK/HP label 列
    colw = (total_w - col0) // 4

    # x 坐标
    xs = [tx1, tx1 + col0, tx1 + col0 + colw, tx1 + col0 + colw * 2, tx1 + col0 + colw * 3, tx2]
    # y 坐标
    head_h = 34
    row_h = (total_h - head_h) // 2
    ys = [ty1, ty1 + head_h, ty1 + head_h + row_h, ty2]

    # 表头底色（除 label 列之外）
    d.rectangle((xs[1], ys[0], xs[-1], ys[1]), fill=head_bg)

    # 画网格线
    for xx in xs:
        d.line((xx, ys[0], xx, ys[-1]), fill=grid, width=2)
    for yy in ys:
        d.line((xs[0], yy, xs[-1], yy), fill=grid, width=2)

    # 表头文字
    headers = ["Base", "Lv90", "Lv100", "Lv120"]
    for i, htxt in enumerate(headers):
        cx1, cx2 = xs[i + 1], xs[i + 2]
        cy1, cy2 = ys[0], ys[1]
        tw = d.textlength(htxt, font=f_small)
        d.text((cx1 + (cx2 - cx1 - tw) / 2, cy1 + 8), htxt, font=f_small, fill=subtext)

    def draw_cell(row: int, col: int, value: str, font, color=text):
        # row: 1=ATK, 2=HP ; col: 0=label, 1..4=data
        x1 = xs[col]
        x2 = xs[col + 1]
        y1 = ys[row]
        y2 = ys[row + 1]
        tw = d.textlength(value, font=font)
        d.text((x1 + (x2 - x1 - tw) / 2, y1 + (y2 - y1 - 18) / 2), value, font=font, fill=color)

    def fmt(v: int | None) -> str:
        return "—" if v is None else str(v)

    # ATK 行
    draw_cell(1, 0, "ATK", f_num, color=text)
    atk_vals = [m.atk["base"], m.atk["90"], m.atk["100"], m.atk["120"]]
    for i, v in enumerate(atk_vals, start=1):
        draw_cell(1, i, fmt(v), f_num, color=text)

    # HP 行
    draw_cell(2, 0, "HP", f_num, color=text)
    hp_vals = [m.hp["base"], m.hp["90"], m.hp["100"], m.hp["120"]]
    for i, v in enumerate(hp_vals, start=1):
        draw_cell(2, i, fmt(v), f_num, color=text)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()