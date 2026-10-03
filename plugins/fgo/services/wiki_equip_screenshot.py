"""fgowiki 礼装页面截图服务(parse API + 本地渲染)— 只截表单区域,跳过标题/导航栏"""
from __future__ import annotations

from playwright.async_api import Page

from . import api_render

VIEWPORT_W = 800
VIEWPORT_H = 1000

_BOUNDS_JS = """() => {
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
}"""


async def capture_equip_page(keyword: str, *, timeout_ms: int = 15000) -> bytes | None:
    """截取 fgowiki 礼装页面表单区域，返回 PNG 字节。查不到返回 None。"""
    html = await api_render.fetch_page_html(keyword)
    if not html:
        return None

    page = await api_render.render_page(html, viewport_w=VIEWPORT_W, viewport_h=VIEWPORT_H)
    if page is None:
        return None

    try:
        # 定位裁剪边界：表头 → 成长曲线前
        bounds = await page.evaluate(_BOUNDS_JS)
        if not bounds:
            return None

        clip_w = int(min(bounds["pageW"], VIEWPORT_W))
        clip_h = int(min(bounds["height"], 3000))
        return await api_render.capture_region(page, bounds["y"], clip_h, clip_w)

    except Exception:
        return None
    finally:
        await page.close()
