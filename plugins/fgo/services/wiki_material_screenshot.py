"""fgowiki 素材/道具页面截图服务(parse API + 本地渲染)"""
from __future__ import annotations

from playwright.async_api import Page

from . import api_render

VIEWPORT_W = 800
VIEWPORT_H = 1000

_FARM_VIEWPORT_W = 1000


async def _load_material_page(keyword: str, viewport_w: int) -> Page | None:
    """渲染素材页面,返回 page 对象。失败返回 None。"""
    html = await api_render.fetch_page_html(keyword)
    if not html:
        return None
    return await api_render.render_page(html, viewport_w=viewport_w, viewport_h=VIEWPORT_H)


async def capture_material_page(keyword: str, *, timeout_ms: int = 15000) -> bytes | None:
    """截取 fgowiki 素材页面顶部信息框，返回 PNG 字节。查不到返回 None。"""
    page = await _load_material_page(keyword, VIEWPORT_W)
    if not page:
        return None

    try:
        bounds = await page.evaluate("""() => {
            function getY(el) { const r = el.getBoundingClientRect(); return r.y + window.scrollY; }
            function getBottom(el) { const r = el.getBoundingClientRect(); return r.bottom + window.scrollY; }

            const content = document.querySelector('#mw-content-text');
            if (!content) return null;

            const table = content.querySelector('table.wikitable');
            if (!table) return null;

            const tableTop = getY(table);
            const tableBottom = getBottom(table);
            const startY = Math.max(0, tableTop - 2);
            const stopY = tableBottom + 4;

            return { y: startY, height: Math.max(80, stopY - startY) };
        }""")

        if not bounds:
            return None

        return await api_render.capture_region(
            page, bounds["y"], int(bounds["height"]), VIEWPORT_W
        )

    except Exception:
        return None
    finally:
        await page.close()


async def capture_material_farming(keyword: str, *, timeout_ms: int = 15000) -> bytes | None:
    """截取 fgowiki 素材页面的「主要掉落关卡」表，按 AP 效率排序只取前 3 行。查不到返回 None。"""
    page = await _load_material_page(keyword, _FARM_VIEWPORT_W)
    if not page:
        return None

    try:
        table_index = await page.evaluate("""() => {
            const content = document.querySelector('#mw-content-text');
            if (!content) return -1;

            function findTable(start, depth) {
                if (!start || depth > 5) return null;
                let cur = start;
                while (cur && cur.tagName !== 'H2') {
                    if (cur.tagName === 'TABLE' && cur.classList.contains('wikitable')
                        && cur.getBoundingClientRect().height >= 20) return cur;
                    if (cur.firstElementChild) {
                        const found = findTable(cur.firstElementChild, depth + 1);
                        if (found) return found;
                    }
                    cur = cur.nextElementSibling;
                }
                return null;
            }

            const h2s = content.querySelectorAll('h2');
            for (const h2 of h2s) {
                if (!h2.textContent.includes('主要掉落关卡')) continue;
                const table = findTable(h2.nextElementSibling, 0);
                if (!table) continue;

                // 解除容器限制
                let p = table.parentElement;
                while (p && p !== content) {
                    p.style.maxHeight = 'none';
                    p.style.overflow = 'visible';
                    p = p.parentElement;
                }

                // ── 找到 AP 效率列：扫 tbody 第一行找小数（AP均值通常是 10~200 之间的小数） ──
                let apCol = -1;
                const tbody = table.querySelector('tbody');
                const firstRow = tbody ? tbody.querySelector('tr') : table.querySelectorAll('tr')[1];
                if (firstRow) {
                    const tds = firstRow.querySelectorAll('td');
                    for (let i = 0; i < tds.length; i++) {
                        const v = parseFloat(tds[i].textContent.trim());
                        // AP/个 的特征：正小数，不含百分号，值通常在 5~500 之间
                        if (!isNaN(v) && v > 0 && v < 500
                            && tds[i].textContent.trim().indexOf('.') > 0
                            && tds[i].textContent.trim().indexOf('%') < 0) {
                            apCol = i;
                            break;
                        }
                    }
                }
                if (apCol < 0) apCol = 5; // fallback

                // ── 收集并排序数据行 ──
                const rows = tbody ? Array.from(tbody.querySelectorAll('tr')) : Array.from(table.querySelectorAll('tr')).slice(1);

                const scored = [];
                rows.forEach((tr, idx) => {
                    const tds = tr.querySelectorAll('td');
                    if (tds.length <= apCol) return;
                    const val = parseFloat(tds[apCol].textContent.trim());
                    if (isNaN(val)) return;
                    scored.push({tr, val, idx});
                });

                // 按 AP/个 升序（越小效率越高）
                scored.sort((a, b) => a.val - b.val);

                // ── 只保留表头 + 前 3 行 ──
                const keep = new Set(scored.slice(0, 3).map(s => s.tr));
                rows.forEach(tr => {
                    if (!keep.has(tr)) tr.style.display = 'none';
                });

                // 统计 table 在页面中的索引
                const all = content.querySelectorAll('table.wikitable');
                for (let i = 0; i < all.length; i++) {
                    if (all[i] === table) return i;
                }
            }
            return -1;
        }""")

        if table_index < 0:
            return None

        png = await page.locator("table.wikitable").nth(table_index).screenshot(type="png")
        return png

    except Exception:
        return None
    finally:
        await page.close()
