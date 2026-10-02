"""fgowiki 从者卡面立绘图片提取服务(parse API 纯文本解析)

从 parse API 拿到的页面 HTML 中解析「文件:」链接，按文件名模式匹配阶段
并下载原图。不再打开浏览器页面,匹配逻辑与原 DOM 扫描版本一致。
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import unquote

from . import api_render

# 图片缓存目录
CARD_CACHE_DIR = Path(__file__).parent.parent / "data" / "cache" / "card"
CARD_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 排除关键词(不应匹配的图片类型)
EXCLUDE = ["愚人节", "model_", "模型", "图标", "指令卡", "职阶", "阶职", "冠位", "Buster", "Arts", "Quick"]

# 灵衣关键词
COSTUME_PATTERNS = ["灵衣", "霊衣", "Costume", "costume"]


def _stage_patterns(cn_name: str) -> dict[str, list[str]]:
    """阶段关键词映射(末尾的「从者名+数字」兜底模式,如 玄奘三藏1.png)。"""
    return {
        "1": ["初期", "初始", "卡面1", "卡面 1", "Stage 1", "stage 1", "Stage1", "stage1", cn_name + "1"],
        "2": ["一破", "卡面2", "卡面 2", "Stage 2", "stage 2", "Stage2", "stage2", "二破", cn_name + "2"],
        "3": ["三破", "卡面3", "卡面 3", "Stage 3", "stage 3", "Stage3", "stage3", cn_name + "3"],
        "4": ["満破", "满破", "卡面4", "卡面 4", "Stage 4", "stage 4", "Stage4", "stage4", "四破", cn_name + "4"],
    }


def _thumb_to_full_url(url: str) -> str:
    """将 MediaWiki 缩略图 URL 转为原图 URL。

    缩略图格式：
      https://fgo.wiki/images/thumb/a/ab/file.png/800px-file.png
    原图格式：
      https://fgo.wiki/images/a/ab/file.png
    非缩略图直接返回。
    """
    if "/thumb/" not in url:
        return url
    # 去掉 /thumb 路径段
    url = url.replace("/thumb/", "/")
    # 去掉末尾的 /{size}px-{filename} 段
    parts = url.rsplit("/", 1)
    if len(parts) == 2 and re.match(r"\d+px-", parts[1]):
        url = parts[0]
    return url


async def _download_image(url: str) -> bytes | None:
    """下载图片，优先从本地缓存读取。"""
    cache_fn = CARD_CACHE_DIR / f"{hashlib.sha1(url.encode('utf-8')).hexdigest()}.img"
    if cache_fn.exists() and cache_fn.stat().st_size > 0:
        return cache_fn.read_bytes()

    try:
        async with api_render._session(total=20) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.read()
    except Exception:
        return None

    try:
        cache_fn.write_bytes(data)
    except OSError:
        pass
    return data


async def get_servant_card_image(
    cn_name: str, card_spec: str, *, timeout_ms: int = 15000
) -> bytes | None:
    """从 fgowiki 从者页面提取指定阶段的卡面原图。

    策略：解析页面 HTML 中所有 href="文件:..." 链接，
    匹配文件名中的 "卡面{N}" 或 "灵衣" 模式，提取对应图片。

    Args:
        cn_name: 从者中文名
        card_spec: 阶段编号 ("1"-"4") 或 "灵衣"
        timeout_ms: 页面加载超时（毫秒）

    Returns:
        PNG 图片 bytes，失败返回 None
    """
    try:
        html = await api_render.fetch_page_html(cn_name)
        if not html:
            return None

        # 1. 解析所有「文件:」链接
        candidates: list[dict] = []
        for m in re.finditer(
            r'<a[^>]+href="([^"]*%E6%96%87%E4%BB%B6:[^"]*)"[^>]*>(.*?)</a>',
            html,
            re.S,
        ):
            href, inner = m.group(1), m.group(2)
            filename = unquote(href)
            idx = filename.find("文件:")
            if idx == -1:
                continue
            filename = filename[idx + 3:]

            # 排除无关图片类型
            if any(kw in filename for kw in EXCLUDE):
                continue

            # 获取 <a> 内的 <img>
            img_m = re.search(r"<img[^>]*>", inner)
            if not img_m:
                continue
            img_tag = img_m.group(0)
            src_m = re.search(r'\bsrc="([^"]+)"', img_tag)
            if not src_m:
                src_m = re.search(r'\bdata-src="([^"]+)"', img_tag)
            if not src_m:
                continue
            src = src_m.group(1)
            if "data:" in src or "svg" in src:
                continue

            # 排除太小的图
            w_m = re.search(r'\bwidth="(\d+)"', img_tag)
            h_m = re.search(r'\bheight="(\d+)"', img_tag)
            w = int(w_m.group(1)) if w_m else 0
            h = int(h_m.group(1)) if h_m else 0
            if w < 150 and h < 150:
                continue

            # 解析阶段编号
            card_num = None
            is_costume = False

            # 检查是否是灵衣
            for kw in COSTUME_PATTERNS:
                if kw in filename:
                    is_costume = True
                    cm = re.search(kw + r"\s*(\d+)", filename)
                    card_num = int(cm.group(1)) if cm else 1
                    break

            # 检查是否是阶段卡面
            if not is_costume:
                for stage, patterns in _stage_patterns(cn_name).items():
                    for p in patterns:
                        if p in filename:
                            card_num = int(stage)
                            break
                    if card_num is not None:
                        break

            # 如果没有匹配到阶段编号，继续（可能是其他无关图片）
            if card_num is None:
                continue

            candidates.append({
                "filename": filename,
                "src": src,
                "card_num": card_num,
                "is_costume": is_costume,
                "width": w,
                "height": h,
            })

        if not candidates:
            return None

        # 2. 按 spec 筛选
        if card_spec == "灵衣":
            matches = [c for c in candidates if c["is_costume"]]
        else:
            target_num = int(card_spec)
            matches = [c for c in candidates if not c["is_costume"] and c["card_num"] == target_num]

        if not matches:
            # 回退：按位置索引
            if card_spec != "灵衣":
                target_num = int(card_spec)
                non_costume = [c for c in candidates if not c["is_costume"]]
                # 去重 card_num 后按 card_num 排序
                seen: set[int] = set()
                unique = []
                for c in non_costume:
                    if c["card_num"] not in seen:
                        seen.add(c["card_num"])
                        unique.append(c)
                unique.sort(key=lambda c: c["card_num"])
                idx = target_num - 1
                if 0 <= idx < len(unique):
                    matches = [unique[idx]]

        if not matches:
            return None

        # 3. 取分辨率最高的
        matches.sort(key=lambda c: -(c["width"] * c["height"]))
        img_src = matches[0]["src"]

        # 4. 缩略图 → 原图 URL
        full_url = _thumb_to_full_url(img_src)
        print(f"[wiki_card] 卡面图片 URL: {full_url}")

        # 5. 下载图片
        return await _download_image(full_url)

    except Exception:
        return None
