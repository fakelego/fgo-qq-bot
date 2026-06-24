"""fgowiki 页面截图服务（Playwright 无头浏览器）"""
from __future__ import annotations

import asyncio
from io import BytesIO
from urllib.parse import quote

from playwright.async_api import async_playwright, Browser, Page

_browser: Browser | None = None
_browser_lock = asyncio.Lock()


async def _get_browser() -> Browser:
    """获取或创建共享浏览器实例"""
    global _browser
    async with _browser_lock:
        if _browser is None or not _browser.is_connected():
            pw = await async_playwright().start()
            _browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
        return _browser


def _build_fgowiki_urls(cn_name: str) -> list[str]:
    """构造可能的 fgowiki 页面 URL（按优先级排列）"""
    encoded = quote(cn_name)
    return [
        f"https://fgo.wiki/w/{encoded}",           # 直接页面
        f"https://fgo.wiki/index.php?search={encoded}",  # 搜索页
    ]


async def capture_servant_page(cn_name: str, *, timeout_ms: int = 15000) -> bytes | None:
    """截取 fgowiki 从者页面截图，返回 PNG bytes。"""
    browser = await _get_browser()
    page: Page = await browser.new_page(
        viewport={"width": 840, "height": 1200},
        device_scale_factor=1,
    )

    try:
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

        # 等页面渲染完成
        await asyncio.sleep(1.5)

        # fgowiki 的正文区域
        selectors = [
            "#bodyContent",
            "#mw-content-text",
            ".mw-parser-output",
            "#content",
            "article",
        ]
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    box = await el.bounding_box()
                    if box and box["height"] > 100:
                        screenshot = await el.screenshot(type="png")
                        return screenshot
            except Exception:
                continue

        # 回退：全页截图
        screenshot = await page.screenshot(type="png", full_page=True)
        return screenshot

    finally:
        await page.close()


async def close_browser():
    """关闭浏览器（用于应用退出时清理）"""
    global _browser
    if _browser and _browser.is_connected():
        await _browser.close()
        _browser = None
