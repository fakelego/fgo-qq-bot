"""fgowiki 从者卡面立绘图片提取服务

从 fgowiki 从者页面查找卡面/灵衣文件链接，按文件名模式匹配阶段并下载原图。
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from pathlib import Path

import aiohttp
from playwright.async_api import Page

from .wiki_screenshot import (
    _get_browser,
    _hide_sidebar_and_expand,
    _force_load_all_images,
    _build_fgowiki_urls,
)

# 图片缓存目录
CARD_CACHE_DIR = Path(__file__).parent.parent / "data" / "cache" / "card"
CARD_CACHE_DIR.mkdir(parents=True, exist_ok=True)


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
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20)
        ) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.read()
    except Exception:
        return None

    cache_fn.write_bytes(data)
    return data


async def get_servant_card_image(
    cn_name: str, card_spec: str, *, timeout_ms: int = 15000
) -> bytes | None:
    """从 fgowiki 从者页面提取指定阶段的卡面原图。

    策略：搜索页面中所有 <a> 标签的 href="文件:..." 链接，
    匹配文件名中的 "卡面{N}" 或 "灵衣" 模式，提取对应图片。

    Args:
        cn_name: 从者中文名
        card_spec: 阶段编号 ("1"-"4") 或 "灵衣"
        timeout_ms: 页面加载超时（毫秒）

    Returns:
        PNG 图片 bytes，失败返回 None
    """
    browser = await _get_browser()
    page: Page = await browser.new_page(
        viewport={"width": 1100, "height": 1200},
        device_scale_factor=1,
    )

    try:
        # 1. 加载从者页面
        urls = _build_fgowiki_urls(cn_name)
        for url in urls:
            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            except Exception:
                continue
            if resp and resp.status in (200, 304):
                break
        else:
            return None

        await _hide_sidebar_and_expand(page)
        await asyncio.sleep(0.3)

        # 关闭弹窗
        try:
            await page.evaluate("""() => {
                document.querySelectorAll('.mw-dialog,[role="dialog"]').forEach(e => e.remove());
            }""")
        except Exception:
            pass

        await _force_load_all_images(page)

        # 2. 搜索文件链接中的卡面/灵衣图片
        img_src = await page.evaluate(
            """([spec, cnName]) => {
            // 排除关键词（不应匹配的图片类型）
            const EXCLUDE = ['愚人节', 'model_', '模型', '图标', '指令卡', '职阶', '阶职', '冠位', 'Buster', 'Arts', 'Quick'];
            // 阶段关键词映射（末尾的「从者名+数字」兜底模式，如 玄奘三藏1.png）
            const STAGE_PATTERNS = {
                '1': ['初期', '初始', '卡面1', '卡面 1', 'Stage 1', 'stage 1', 'Stage1', 'stage1', cnName + '1'],
                '2': ['一破', '卡面2', '卡面 2', 'Stage 2', 'stage 2', 'Stage2', 'stage2', '二破', cnName + '2'],
                '3': ['三破', '卡面3', '卡面 3', 'Stage 3', 'stage 3', 'Stage3', 'stage3', cnName + '3'],
                '4': ['満破', '满破', '卡面4', '卡面 4', 'Stage 4', 'stage 4', 'Stage4', 'stage4', '四破', cnName + '4'],
            };
            const COSTUME_PATTERNS = ['灵衣', '霊衣', 'Costume', 'costume'];

            // 收集所有 "文件:" 链接
            const allLinks = document.querySelectorAll('a[href*="%E6%96%87%E4%BB%B6:"]');
            const candidates = [];

            for (const a of allLinks) {
                const href = a.getAttribute('href') || '';
                let filename = '';
                try {
                    filename = decodeURIComponent(href);
                } catch (e) {
                    filename = href;
                }
                const idx = filename.indexOf('文件:');
                if (idx === -1) continue;
                filename = filename.substring(idx + 3);

                // 排除无关图片类型
                let excluded = false;
                for (const kw of EXCLUDE) {
                    if (filename.includes(kw)) { excluded = true; break; }
                }
                if (excluded) continue;

                // 获取 <a> 内的 <img>
                const img = a.querySelector('img');
                if (!img) continue;
                const src = img.src || img.getAttribute('data-src') || '';
                if (!src || src.includes('data:') || src.includes('svg')) continue;

                // 排除太小的图
                const w = img.naturalWidth || img.width || 0;
                const h = img.naturalHeight || img.height || 0;
                if (w < 150 && h < 150) continue;

                // 解析阶段编号
                let cardNum = null;
                let isCostume = false;

                // 检查是否是灵衣
                for (const kw of COSTUME_PATTERNS) {
                    if (filename.includes(kw)) {
                        isCostume = true;
                        const cm = filename.match(new RegExp(kw + '\\\\s*(\\\\d+)'));
                        cardNum = cm ? parseInt(cm[1]) : 1;
                        break;
                    }
                }

                // 检查是否是阶段卡面
                if (!isCostume) {
                    for (const [stage, patterns] of Object.entries(STAGE_PATTERNS)) {
                        for (const p of patterns) {
                            if (filename.includes(p)) {
                                cardNum = parseInt(stage);
                                break;
                            }
                        }
                        if (cardNum !== null) break;
                    }
                }

                // 如果没有匹配到阶段编号，继续（可能是其他无关图片）
                if (cardNum === null) continue;

                candidates.push({
                    filename: filename,
                    src: src,
                    cardNum: cardNum,
                    isCostume: isCostume,
                    width: w,
                    height: h,
                });
            }

            if (candidates.length === 0) return null;

            // 按 spec 筛选
            let matches;
            if (spec === '灵衣') {
                matches = candidates.filter(c => c.isCostume);
            } else {
                const targetNum = parseInt(spec);
                matches = candidates.filter(c => !c.isCostume && c.cardNum === targetNum);
            }

            if (matches.length === 0) {
                // 回退：按位置索引
                if (spec !== '灵衣') {
                    const targetNum = parseInt(spec);
                    const nonCostume = candidates.filter(c => !c.isCostume);
                    // 去重 cardNum 后按 cardNum 排序
                    const seen = new Set();
                    const unique = [];
                    for (const c of nonCostume) {
                        if (!seen.has(c.cardNum)) {
                            seen.add(c.cardNum);
                            unique.push(c);
                        }
                    }
                    unique.sort((a, b) => a.cardNum - b.cardNum);
                    const idx = targetNum - 1;
                    if (idx >= 0 && idx < unique.length) {
                        matches = [unique[idx]];
                    }
                }
            }

            if (matches.length === 0) return null;

            // 取分辨率最高的
            matches.sort((a, b) => (b.width * b.height) - (a.width * a.height));
            return matches[0].src;
        }""",
            [card_spec, cn_name],
        )

        if not img_src:
            return None

        # 3. 缩略图 → 原图 URL
        full_url = _thumb_to_full_url(img_src)
        print(f"[wiki_card] 卡面图片 URL: {full_url}")

        # 4. 下载图片
        data = await _download_image(full_url)
        return data

    except Exception:
        return None
    finally:
        await page.close()
