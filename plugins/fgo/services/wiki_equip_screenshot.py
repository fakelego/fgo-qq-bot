"""fgowiki 礼装页面截图服务 — 只截表单区域，跳过标题/导航栏"""
from __future__ import annotations

import asyncio
from urllib.parse import quote

from playwright.async_api import Browser, Page

from .wiki_screenshot import _get_browser, _hide_sidebar_and_expand, _force_load_all_images

VIEWPORT_W = 800
VIEWPORT_H = 1000


async def capture_equip_page(keyword: str, *, timeout_ms: int = 15000) -> bytes | None:
    """截取 fgowiki 礼装页面表单区域，返回 PNG 字节。查不到返回 None。"""
    encoded = quote(keyword)
    urls = [
        f"https://fgo.wiki/w/{encoded}",
        f"https://fgo.wiki/index.php?search={encoded}",
    ]

    browser = await _get_browser()
    page: Page = await browser.new_page(
        viewport={"width": VIEWPORT_W, "height": VIEWPORT_H},
        device_scale_factor=1,
    )

    try:
        # 加载页面
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
        await _force_load_all_images(page)

        # 定位裁剪边界：表头 → 成长曲线前
        bounds = await page.evaluate("""() => {
            function getY(el) { const r = el.getBoundingClientRect(); return r.y + window.scrollY; }

            const content = document.querySelector('#mw-content-text');
            if (!content) return null;

            const table = content.querySelector('table.wikitable.nomobile');
            if (!table) return null;
            const tableRect = table.getBoundingClientRect();
            const tableTop = tableRect.y + window.scrollY;
            const tableBottom = tableRect.bottom + window.scrollY;

            let stopY = tableBottom;

            // 找到 "成长曲线" 行，截到该行之前（保留出场角色及角色名列表）
            const rows = table.querySelectorAll('tr');
            for (const tr of rows) {
                const text = tr.textContent.trim();
                if (text.startsWith('成长曲线') && tr.getBoundingClientRect().height < 60) {
                    stopY = getY(tr) - 1;
                    break;
                }
            }

            return {
                y: tableTop,
                height: Math.max(100, stopY - tableTop),
                pageW: document.body.scrollWidth
            };
        }""")

        if not bounds:
            return None

        # 截图：只截表单区域
        clip = {
            "x": 0,
            "y": bounds["y"],
            "width": bounds["pageW"],
            "height": min(bounds["height"], 3000),
        }
        png = await page.screenshot(type="png", clip=clip, full_page=True)
        return png

    except Exception:
        return None
    finally:
        await page.close()
