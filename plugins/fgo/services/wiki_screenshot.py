"""fgowiki 页面截图服务（Playwright 无头浏览器）"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import quote

import traceback
from io import BytesIO

from PIL import Image as PilImage
from playwright.async_api import async_playwright, Browser, Page

_browser: Browser | None = None
_browser_lock = asyncio.Lock()

VIEWPORT_W = 1100
VIEWPORT_H = 1200
MAX_CLIP_H = 1400
SECTION_GAP = 12


@dataclass
class SectionImage:
    title: str
    png_bytes: bytes


async def _get_browser() -> Browser:
    global _browser
    async with _browser_lock:
        if _browser is None or not _browser.is_connected():
            pw = await async_playwright().start()
            _browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
            )
        return _browser


def _build_fgowiki_urls(cn_name: str) -> list[str]:
    encoded = quote(cn_name)
    return [
        f"https://fgo.wiki/w/{encoded}",
        f"https://fgo.wiki/index.php?search={encoded}",
    ]


async def _hide_sidebar_and_expand(page: Page) -> None:
    await page.add_style_tag(content="""
        #mw-navigation, #mw-panel, #p-logo, #column-one,
        .mw-sidebar, .sidebar, #siteNotice, #mw-head,
        #mw-page-base, #footer-places, #footer-icons,
        #footer-info, #catlinks { display: none !important; }
        #content, #bodyContent, #mw-content-text, .mw-body {
            margin-left: 0 !important;
            padding-left: 12px !important;
            max-width: 100% !important;
        }
        .mw-parser-output { max-width: 100% !important; }
        .editsection, .mw-editsection { display: none !important; }
        /* 隐藏广告 */
        iframe, [id*="google_ads"], [class*="adsbygoogle"] { display: none !important; }
    """)


async def _force_load_all_images(page: Page) -> None:
    await page.evaluate("""async () => {
        const delay = (ms) => new Promise(r => setTimeout(r, ms));
        const totalHeight = document.body.scrollHeight;
        for (let y = 0; y < totalHeight; y += 600) {
            window.scrollTo(0, y);
            await delay(150);
        }
        window.scrollTo(0, 0);
        await delay(300);
    }""")
    await page.evaluate("""() => {
        document.querySelectorAll('img').forEach(img => {
            const dataSrc = img.getAttribute('data-src');
            if (dataSrc && !img.src) img.src = dataSrc;
            img.loading = 'eager';
        });
    }""")
    try:
        await page.wait_for_function("""() => {
            const imgs = Array.from(document.querySelectorAll('img'));
            const visible = imgs.filter(i => i.offsetParent !== null && i.src);
            return visible.length === 0 || visible.every(i => i.complete);
        }""", timeout=8000)
    except Exception:
        pass
    await asyncio.sleep(0.5)


async def capture_servant_sections(
    cn_name: str, *, timeout_ms: int = 20000
) -> list[SectionImage]:
    try:
        browser = await _get_browser()
        print(f"[wiki_screenshot] 浏览器就绪")
        page: Page = await browser.new_page(
            viewport={"width": VIEWPORT_W, "height": VIEWPORT_H},
            device_scale_factor=1,
        )

        urls = _build_fgowiki_urls(cn_name)
        print(f"[wiki_screenshot] 加载页面: {urls[0]}")
        # 1. 加载页面
        urls = _build_fgowiki_urls(cn_name)
        for url in urls:
            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            except Exception:
                continue
            if resp and resp.status in (200, 304):
                break
        else:
            return []

        await _hide_sidebar_and_expand(page)
        await asyncio.sleep(0.5)
        # 关闭可能的弹窗
        try:
            await page.evaluate("""() => {
                // 只关明确的浮动弹窗，不碰内容区的元素
                document.querySelectorAll('.mw-dialog,[role="dialog"]').forEach(e => e.remove());
            }""")
        except Exception:
            pass
        await _force_load_all_images(page)

        # 2. 收集章节分界点
        heading_data = await page.evaluate("""() => {
            const content = document.querySelector('#mw-content-text');
            if (!content) return [];
            function getY(el) { const r = el.getBoundingClientRect(); return r.y + window.scrollY; }
            const results = [];
            const h2s = content.querySelectorAll('h2');
            h2s.forEach((h2) => {
                if (h2.closest('#toc, .toc, .toctoggle')) return;
                const text = h2.textContent.trim();
                if (text === '目录') return;
                if (h2.getBoundingClientRect().height < 10) return;
                if (text === '技能' || text.includes('技能')) {
                    let cur = h2.nextElementSibling;
                    while (cur && cur.tagName !== 'H2') {
                        if (cur.tagName === 'H3') {
                            const h3t = cur.textContent.trim();
                            if (h3t) results.push({title: h3t, y: getY(cur)});
                            if (h3t.includes('保有技能') || h3t.includes('持有技能')) {
                                let sub = cur.nextElementSibling;
                                while (sub && sub.tagName !== 'H3' && sub.tagName !== 'H2') {
                                    if (sub.tagName === 'P') {
                                        const m = sub.textContent.trim().match(/技能\\d+/);
                                        if (m) results.push({title: m[0], y: getY(sub)});
                                    }
                                    sub = sub.nextElementSibling;
                                }
                            }
                        }
                        cur = cur.nextElementSibling;
                    }
                } else {
                    results.push({title: text, y: getY(h2)});
                }
            });
            return results;
        }""")

        if not heading_data:
            png = await page.screenshot(type="png", full_page=True)
            return [SectionImage(title="从者页面", png_bytes=png)]

        page_bottom = await page.evaluate("document.body.scrollHeight")

        # 3. 收集 tabber：{ heading文本 -> [(标签, tab_id)] }
        raw_tabbers = await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('.tabber').forEach(tb => {
                let prev = tb.previousElementSibling;
                let heading = '';
                while (prev) {
                    if (['H2','H3'].includes(prev.tagName)) {
                        heading = prev.textContent.trim(); break;
                    }
                    if (prev.tagName === 'P') {
                        const txt = prev.textContent.trim();
                        // 跳过空 P 和装 CSS/JS 代码的 P
                        if (txt && !txt.startsWith('.') && !txt.startsWith('{') && !txt.startsWith('function') && !txt.startsWith('curr_audio') && txt.length < 200) {
                            heading = txt; break;
                        }
                    }
                    prev = prev.previousElementSibling;
                }
                const tabs = Array.from(tb.querySelectorAll('.tabber__tab')).map(t => ({
                    label: t.textContent.trim(),
                    panelId: t.id.replace('-label', ''),
                }));
                results.push({heading, tabs});
            });
            return results;
        }""")
        tabber_map: dict[str, list[tuple[str, str]]] = {}
        for entry in raw_tabbers:
            h = entry["heading"]
            for t in entry["tabs"]:
                lbl = t["label"]
                pid = t["panelId"]
                if pid and h:
                    tabber_map.setdefault(h, []).append((lbl, pid))

        # 4. JS：递归找表格，可限定 panel id
        async def _find_table_indices(page: Page, title: str, panel_id: str | None, next_title: str) -> list[int]:
            """返回匹配标题下所有可见 nomobile 表格的全局索引列表。遇到 next_title 标题时停止。"""
            escaped = title.replace("\\", "\\\\").replace("'", "\\'")
            next_escaped = next_title.replace("\\", "\\\\").replace("'", "\\'")
            pid = panel_id or ""
            return await page.evaluate("""([t, pid, nxt]) => {
                const content = document.querySelector('#mw-content-text');
                if (!content) return [];

                function getY(el) { const r = el.getBoundingClientRect(); return r.y + window.scrollY; }

                // 用与 heading_data 相同的方式找标题元素
                const h2s = content.querySelectorAll('h2');
                const h3s = content.querySelectorAll('h3');
                const ps = content.querySelectorAll('p');
                const all = [...h2s, ...h3s, ...ps].sort((a,b) => getY(a) - getY(b));

                let heading = null;
                for (const e of all) {
                    const txt = e.textContent.trim();
                    if (txt === t || txt.startsWith(t)) { heading = e; break; }
                }
                if (!heading) return [];

                function isHeading(el) { return ['H2','H3'].includes(el.tagName); }
                function matchesTitle(el, t) { return el.textContent.trim() === t || el.textContent.trim().startsWith(t); }

                // 确定 stopTags：P 标题用 P 停止，H2/H3 标题不用
                const stopTags = heading.tagName === 'P' ? ['H2','H3','P'] : ['H2','H3'];

                function findTables(start, panel, depth) {
                    if (!start || depth > 5) return [];
                    const results = [];
                    let cur = start;
                    // 只在顶层检查 P 标签，嵌套内忽略（tabber 面板内可能有 P）
                    const stop = depth === 0 ? stopTags : ['H2','H3'];
                    while (cur && !stop.includes(cur.tagName)) {
                        // 遇到下一个标题则停止
                        if (nxt && stop.includes(cur.tagName) && matchesTitle(cur, nxt)) break;
                        if (cur.tagName === 'TABLE' && cur.classList.contains('nomobile') && cur.getBoundingClientRect().height >= 20) {
                            // 排除弹窗/浮层内的表格
                            const bad = cur.closest('.cbox,.mw-dialog,.popup,.modal,.overlay,[role="dialog"],[style*="position: fixed"],[style*="position:fixed"]');
                            if (bad) { cur = cur.nextElementSibling; continue; }
                            // 如果指定了 panel，检查该 table 是否在目标 panel 内
                            if (!panel || cur.closest('#' + CSS.escape(panel))) {
                                results.push(cur);
                            }
                        }
                        if (cur.firstElementChild && !['TABLE','P','A','BUTTON','SPAN'].includes(cur.tagName)) {
                            results.push(...findTables(cur.firstElementChild, panel, depth + 1));
                        }
                        cur = cur.nextElementSibling;
                    }
                    return results;
                }

                const tables = findTables(heading.nextElementSibling, pid || null, 0);
                const allTbls = document.querySelectorAll('table.wikitable.nomobile');
                const indices = [];
                for (const t of tables) {
                    for (let i = 0; i < allTbls.length; i++) {
                        if (allTbls[i] === t) { indices.push(i); break; }
                    }
                }
                return indices;
            }""", [escaped, pid])

        def _merge_pngs(pngs: list[bytes], gap: int = 4) -> bytes:
            """垂直拼接多张 PNG"""
            if len(pngs) == 1:
                return pngs[0]
            images = [PilImage.open(BytesIO(p)) for p in pngs]
            w = max(im.width for im in images)
            total_h = sum(im.height for im in images) + gap * (len(images) - 1)
            merged = PilImage.new("RGBA", (w, total_h), (255, 255, 255, 255))
            y = 0
            for im in images:
                merged.paste(im, (0, y))
                y += im.height + gap
            buf = BytesIO()
            merged.save(buf, format="PNG")
            return buf.getvalue()

        async def _screenshot_indices(indices: list[int], merge: bool = False) -> list[bytes]:
            results = []
            for idx in indices:
                try:
                    png = await page.locator("table.wikitable.nomobile").nth(idx).screenshot(type="png")
                    results.append(png)
                except Exception:
                    pass
            if merge and len(results) > 1:
                return [_merge_pngs(results)]
            return results

        # 5. 逐章节截图
        sections: list[SectionImage] = []

        def _is_table_section(title: str) -> bool:
            return any(title.startswith(p) for p in [
                "宝具", "保有技能", "持有技能", "技能",
                "职阶技能", "追加技能", "资料",
            ])

        def _is_multi_table(title: str) -> bool:
            return title.startswith("追加技能")

        # 不截图的无效板块
        SKIP_SECTIONS = {"相关礼装", "语音", "成长曲线", "国服未来Pick Up情况", "注释和链接", "愚人节", "注释和参考"}

        i = 0
        while i < len(heading_data):
            hd = heading_data[i]
            y_start = hd["y"]
            y_end = heading_data[i + 1]["y"] - SECTION_GAP if i + 1 < len(heading_data) else page_bottom
            section_h = y_end - y_start
            if section_h < 40:
                i += 1
                continue

            title = hd["title"]
            if title in SKIP_SECTIONS:
                i += 1
                continue

            if _is_table_section(title):
                nxt = heading_data[i + 1]["title"] if i + 1 < len(heading_data) else ""

                # 找匹配的 tabber
                matched_tabber = None
                for h_text, tabs in tabber_map.items():
                    if h_text.startswith(title) or title.startswith(h_text):
                        matched_tabber = tabs
                        break

                if matched_tabber:
                    for lbl, panel_id in matched_tabber:
                        await page.evaluate("(pid) => { location.hash = pid; }", panel_id)
                        await asyncio.sleep(0.4)
                        indices = await _find_table_indices(page, title, panel_id, nxt)
                        if indices:
                            merge = _is_multi_table(title)
                            pngs = await _screenshot_indices(indices, merge=merge)
                        else:
                            # 无表格时回退到 clip 截图（如资料），直接从当前 panel 裁
                            box = await page.evaluate(
                                "(pid) => { const p = document.getElementById(pid); if (!p) return null; const r = p.getBoundingClientRect(); return { y: r.y + window.scrollY, h: r.height }; }",
                                panel_id,
                            )
                            if box:
                                clip_w = int(VIEWPORT_W * 0.75) if title.startswith("资料") else VIEWPORT_W
                                clip = {"x": 0, "y": box["y"], "width": clip_w, "height": min(box["h"], MAX_CLIP_H * 2)}
                                try:
                                    png = await page.screenshot(type="png", clip=clip, full_page=True)
                                    pngs = [png]
                                except Exception:
                                    pngs = []
                            else:
                                pngs = []
                        for j, png in enumerate(pngs):
                            sub = f"({lbl})" if len(matched_tabber) > 1 else ""
                            if len(pngs) > 1 and not _is_multi_table(title):
                                sub += f"-{j+1}"
                            sections.append(SectionImage(title=f"{title}{sub}", png_bytes=png))
                else:
                    if _is_table_section(title):
                        indices = await _find_table_indices(page, title, None, nxt)
                        merge = _is_multi_table(title)
                        pngs = await _screenshot_indices(indices, merge=merge)
                        for j, png in enumerate(pngs):
                            sections.append(SectionImage(title=title, png_bytes=png))
                    else:
                        # profile 无 tabber，走普通 clip
                        escaped_title = title.replace("\\", "\\\\").replace("'", "\\'")
                        nxt_esc = nxt.replace("\\", "\\\\").replace("'", "\\'")
                        bounds = await page.evaluate("""([t, nxt]) => {
                            const content = document.querySelector('#mw-content-text');
                            if (!content) return null;
                            function getY(el) { const r = el.getBoundingClientRect(); return r.y + window.scrollY; }
                            const all = [...content.querySelectorAll('h2'), ...content.querySelectorAll('h3'), ...content.querySelectorAll('p')].sort((a,b) => getY(a) - getY(b));
                            let start = null, end = null;
                            for (const e of all) {
                                const txt = e.textContent.trim();
                                if (txt === t || txt.startsWith(t)) start = getY(e);
                                if (nxt && (txt === nxt || txt.startsWith(nxt))) { end = getY(e); break; }
                            }
                            if (!start) return null;
                            return { y: start, h: (end || (start + 600)) - start - 12 };
                        }""", [escaped_title, nxt_esc])
                        if bounds:
                            y = bounds["y"]
                            h = max(40, bounds["h"])
                            clip_h = min(h, MAX_CLIP_H)
                            clip = {"x": 0, "y": y, "width": VIEWPORT_W, "height": clip_h}
                            try:
                                png = await page.screenshot(type="png", clip=clip, full_page=True)
                                sections.append(SectionImage(title=title, png_bytes=png))
                            except Exception:
                                pass
            else:
                # 非表格章节：重新获取标题当前位置后 clip 截图
                escaped = title.replace("\\", "\\\\").replace("'", "\\'")
                nxt = heading_data[i + 1]["title"] if i + 1 < len(heading_data) else ""
                nxt_esc = nxt.replace("\\", "\\\\").replace("'", "\\'")
                bounds = await page.evaluate("""([t, nxt]) => {
                    const content = document.querySelector('#mw-content-text');
                    if (!content) return null;
                    function getY(el) { const r = el.getBoundingClientRect(); return r.y + window.scrollY; }
                    const h2s = content.querySelectorAll('h2');
                    const h3s = content.querySelectorAll('h3');
                    const ps = content.querySelectorAll('p');
                    const all = [...h2s, ...h3s, ...ps].sort((a,b) => getY(a) - getY(b));
                    let start = null, end = null;
                    for (const e of all) {
                        const txt = e.textContent.trim();
                        if (txt === t || txt.startsWith(t)) start = getY(e);
                        if (nxt && (txt === nxt || txt.startsWith(nxt))) { end = getY(e); break; }
                    }
                    if (!start) return null;
                    return { y: start, h: (end || (start + 600)) - start - 12 };
                }""", [escaped, nxt_esc])
                if not bounds:
                    i += 1
                    continue

                y = bounds["y"]
                h = max(40, bounds["h"])
                clip_h = min(h, MAX_CLIP_H)
                no_split = title.startswith("各阶段") or title.startswith("语音")
                if no_split:
                    clip_h = h

                # 部分章节右侧裁剪
                if title.startswith("素材需求"):
                    clip_w = int(VIEWPORT_W * 0.8)
                elif title.startswith("牵绊") or title.startswith("资料"):
                    clip_w = int(VIEWPORT_W * 0.75)
                else:
                    clip_w = VIEWPORT_W

                clip = {"x": 0, "y": y, "width": clip_w, "height": clip_h}
                try:
                    png = await page.screenshot(type="png", clip=clip, full_page=True)
                    sections.append(SectionImage(title=title, png_bytes=png))
                except Exception:
                    pass

                if not no_split and h > clip_h:
                    remaining = h - clip_h
                    offset_y = y + clip_h
                    while remaining > 0:
                        part_h = min(remaining, MAX_CLIP_H)
                        try:
                            png = await page.screenshot(
                                type="png",
                                clip={"x": 0, "y": offset_y, "width": clip_w, "height": part_h},
                                full_page=True,
                            )
                            sections.append(SectionImage(title=f"{title}(续)", png_bytes=png))
                        except Exception:
                            break
                        remaining -= part_h
                        offset_y += part_h

            i += 1

        if not sections:
            png = await page.screenshot(type="png", full_page=True)
            return [SectionImage(title="从者页面", png_bytes=png)]

        return sections

    except Exception as e:
        print(f"[wiki_screenshot] 截图异常: {type(e).__name__}: {e}")
        traceback.print_exc()
        return []
    finally:
        await page.close()


async def capture_servant_page(cn_name: str, *, timeout_ms: int = 20000) -> bytes | None:
    sections = await capture_servant_sections(cn_name, timeout_ms=timeout_ms)
    return sections[0].png_bytes if sections else None


async def close_browser():
    global _browser
    if _browser and _browser.is_connected():
        await _browser.close()
        _browser = None
