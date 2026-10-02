"""fgowiki 从者页面分节截图服务(parse API + 本地渲染)

流程:parse API 取页面 HTML(缓存 7 天)→ api_render 本地渲染(缓存 CSS/图片)
→ 章节切分 → 表格章节逐表截图 / 非表格章节按标题边界 clip 截图。

与原「打开网页截图」版本的行为一致:tabber 多版本逐面板截图、追加技能多表
合并、超长章节分片加 (续) 后缀、SKIP_SECTIONS 跳过无效板块。
"""
from __future__ import annotations

import traceback
from dataclasses import dataclass
from io import BytesIO

from PIL import Image as PilImage
from playwright.async_api import Page

from . import api_render

VIEWPORT_W = 1100
VIEWPORT_H = 1200
MAX_CLIP_H = 1400
SECTION_GAP = 12


@dataclass
class SectionImage:
    title: str
    png_bytes: bytes


# 章节收集:与旧版逻辑一致,但标题统一去尾部 [编辑](parse HTML 的编辑链接在
# 标题内,而命令层用 prefix/exact 筛选标题,不去掉会破坏精确匹配)
_HEADING_JS = """() => {
    const content = document.querySelector('#mw-content-text');
    if (!content) return [];
    function getY(el) { const r = el.getBoundingClientRect(); return r.y + window.scrollY; }
    function titleOf(el) {
        const hl = el.querySelector('.mw-headline');
        const t = (hl || el).textContent.trim();
        return t.replace(/\\[编辑\\]\\s*$/, '');
    }
    const results = [];
    const h2s = content.querySelectorAll('h2');
    h2s.forEach((h2) => {
        if (h2.closest('#toc, .toc, .toctoggle')) return;
        const text = titleOf(h2);
        if (text === '目录') return;
        if (h2.getBoundingClientRect().height < 10) return;
        if (text === '技能' || text.includes('技能')) {
            let cur = h2.nextElementSibling;
            while (cur && cur.tagName !== 'H2') {
                if (cur.tagName === 'H3') {
                    const h3t = titleOf(cur);
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
}"""

# tabber 收集:{ 所属标题文本 -> [(标签, panel_id)] }
_TABBER_JS = """() => {
    function titleOf(el) {
        const hl = el.querySelector('.mw-headline');
        const t = (hl || el).textContent.trim();
        return t.replace(/\\[编辑\\]\\s*$/, '');
    }
    const results = [];
    document.querySelectorAll('.tabber').forEach(tb => {
        let prev = tb.previousElementSibling;
        let heading = '';
        while (prev) {
            if (['H2','H3'].includes(prev.tagName)) {
                heading = titleOf(prev); break;
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
}"""

# 找标题下所有可见 nomobile 表格的全局索引(可限定 tabber panel)。
# 渲染时面板已全部展开,无需再切换 location.hash,按 panel id 过滤即可。
_FIND_TABLES_JS = """([t, pid, nxt]) => {
    const content = document.querySelector('#mw-content-text');
    if (!content) return [];

    function getY(el) { const r = el.getBoundingClientRect(); return r.y + window.scrollY; }
    function titleOf(el) {
        const hl = el.querySelector('.mw-headline');
        const txt = (hl || el).textContent.trim();
        return txt.replace(/\\[编辑\\]\\s*$/, '');
    }

    // 用与章节收集相同的方式找标题元素
    const all = [...content.querySelectorAll('h2'), ...content.querySelectorAll('h3'), ...content.querySelectorAll('p')]
        .sort((a,b) => getY(a) - getY(b));

    let heading = null;
    for (const e of all) {
        const txt = titleOf(e);
        if (txt === t || txt.startsWith(t)) { heading = e; break; }
    }
    if (!heading) return [];

    function matchesTitle(el, t) { const txt = titleOf(el); return txt === t || txt.startsWith(t); }

    // 确定 stopTags:P 标题用 P 停止,H2/H3 标题不用
    const stopTags = heading.tagName === 'P' ? ['H2','H3','P'] : ['H2','H3'];

    function findTables(start, panel, depth) {
        if (!start || depth > 5) return [];
        const results = [];
        let cur = start;
        // 只在顶层检查 P 标签,嵌套内忽略(tabber 面板内可能有 P)
        const stop = depth === 0 ? stopTags : ['H2','H3'];
        while (cur && !stop.includes(cur.tagName)) {
            // 遇到下一个标题则停止
            if (nxt && stop.includes(cur.tagName) && matchesTitle(cur, nxt)) break;
            if (cur.tagName === 'TABLE' && cur.classList.contains('nomobile') && cur.getBoundingClientRect().height >= 20) {
                // 排除弹窗/浮层内的表格
                const bad = cur.closest('.cbox,.mw-dialog,.popup,.modal,.overlay,[role="dialog"],[style*="position: fixed"],[style*="position:fixed"]');
                if (bad) { cur = cur.nextElementSibling; continue; }
                // 如果指定了 panel,检查该 table 是否在目标 panel 内
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
}"""

# 非表格章节边界测量:返回 { y, h, secW(章节内表格需求宽度,用于裁左右留白) }
_BOUNDS_JS = """([t, nxt]) => {
    const content = document.querySelector('#mw-content-text');
    if (!content) return null;
    function getY(el) { const r = el.getBoundingClientRect(); return r.y + window.scrollY; }
    function titleOf(el) {
        const hl = el.querySelector('.mw-headline');
        const txt = (hl || el).textContent.trim();
        return txt.replace(/\\[编辑\\]\\s*$/, '');
    }
    const all = [...content.querySelectorAll('h2'), ...content.querySelectorAll('h3'), ...content.querySelectorAll('p')]
        .sort((a,b) => getY(a) - getY(b));
    let start = null, end = null;
    for (const e of all) {
        const txt = titleOf(e);
        if (txt === t || txt.startsWith(t)) start = e;
        if (nxt && (txt === nxt || txt.startsWith(nxt))) { end = e; break; }
    }
    if (!start) return null;

    // 表格「需求宽度」:px 定宽直接取;有 max-width 取 max-width;
    // 纯百分比宽(自适应视口)的不参与
    const widthOf = (els) => {
        let maxW = 0;
        for (const tb of els) {
            const cs = getComputedStyle(tb);
            if (cs.display === 'none' || cs.visibility === 'hidden') continue;
            let w = 0;
            if (cs.width.endsWith('px')) w = parseFloat(cs.width);
            else if (cs.maxWidth.endsWith('px')) w = parseFloat(cs.maxWidth);
            if (w > maxW) maxW = w;
        }
        return maxW;
    };
    const tables = [];
    let el = start.nextElementSibling;
    while (el && el !== end) {
        if (el.tagName === 'TABLE') tables.push(el);
        else tables.push(...el.querySelectorAll('table'));
        el = el.nextElementSibling;
    }
    return { y: getY(start), h: (end ? getY(end) : getY(start) + 600) - getY(start) - 12, secW: widthOf(tables) };
}"""


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


async def _find_table_indices(page: Page, title: str, panel_id: str | None, next_title: str) -> list[int]:
    """返回匹配标题下所有可见 nomobile 表格的全局索引列表。遇到 next_title 标题时停止。"""
    escaped = title.replace("\\", "\\\\").replace("'", "\\'")
    next_escaped = next_title.replace("\\", "\\\\").replace("'", "\\'")
    return await page.evaluate(_FIND_TABLES_JS, [escaped, panel_id or "", next_escaped])


async def _screenshot_indices(page: Page, indices: list[int], merge: bool = False) -> list[bytes]:
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


def _is_table_section(title: str) -> bool:
    return any(title.startswith(p) for p in [
        "宝具", "保有技能", "持有技能", "技能",
        "职阶技能", "追加技能", "资料",
    ])


def _is_multi_table(title: str) -> bool:
    return title.startswith("追加技能")


# 不截图的无效板块
SKIP_SECTIONS = {"相关礼装", "语音", "成长曲线", "国服未来Pick Up情况", "注释和链接", "愚人节", "注释和参考"}


async def capture_servant_sections(
    cn_name: str, *, timeout_ms: int = 20000
) -> list[SectionImage]:
    try:
        html = await api_render.fetch_page_html(cn_name)
        if not html:
            print(f"[wiki_screenshot] 获取页面 HTML 失败: {cn_name}")
            return []

        page = await api_render.render_page(
            html,
            viewport_w=VIEWPORT_W,
            viewport_h=VIEWPORT_H,
            image_timeout=max(45, timeout_ms // 1000),
        )
        if page is None:
            return []

        try:
            # 1. 收集章节分界点
            heading_data = await page.evaluate(_HEADING_JS)

            if not heading_data:
                png = await page.screenshot(type="png", full_page=True)
                return [SectionImage(title="从者页面", png_bytes=png)]

            page_bottom = await page.evaluate("document.body.scrollHeight")

            # 2. 收集 tabber:{ 标题文本 -> [(标签, panel_id)] }
            raw_tabbers = await page.evaluate(_TABBER_JS)
            tabber_map: dict[str, list[tuple[str, str]]] = {}
            for entry in raw_tabbers:
                h = entry["heading"]
                for t in entry["tabs"]:
                    lbl = t["label"]
                    pid = t["panelId"]
                    if pid and h:
                        tabber_map.setdefault(h, []).append((lbl, pid))

            # 3. 逐章节截图
            sections: list[SectionImage] = []

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

                nxt = heading_data[i + 1]["title"] if i + 1 < len(heading_data) else ""

                if _is_table_section(title):
                    # 找匹配的 tabber
                    matched_tabber = None
                    for h_text, tabs in tabber_map.items():
                        if h_text.startswith(title) or title.startswith(h_text):
                            matched_tabber = tabs
                            break

                    if matched_tabber:
                        for lbl, panel_id in matched_tabber:
                            indices = await _find_table_indices(page, title, panel_id, nxt)
                            if indices:
                                merge = _is_multi_table(title)
                                pngs = await _screenshot_indices(page, indices, merge=merge)
                            else:
                                # 无表格时直接对 panel 元素截图(如资料个人资料面板)
                                try:
                                    png = await page.locator(f'[id="{panel_id}"]').screenshot(type="png")
                                    pngs = [png]
                                except Exception:
                                    pngs = []
                            for j, png in enumerate(pngs):
                                sub = f"({lbl})" if len(matched_tabber) > 1 else ""
                                if len(pngs) > 1 and not _is_multi_table(title):
                                    sub += f"-{j+1}"
                                sections.append(SectionImage(title=f"{title}{sub}", png_bytes=png))
                    else:
                        indices = await _find_table_indices(page, title, None, nxt)
                        merge = _is_multi_table(title)
                        pngs = await _screenshot_indices(page, indices, merge=merge)
                        for png in pngs:
                            sections.append(SectionImage(title=title, png_bytes=png))
                else:
                    # 非表格章节:按标题边界 clip 截图,宽度按章节内表格自适应
                    escaped = title.replace("\\", "\\\\").replace("'", "\\'")
                    nxt_esc = nxt.replace("\\", "\\\\").replace("'", "\\'")
                    bounds = await page.evaluate(_BOUNDS_JS, [escaped, nxt_esc])
                    if not bounds:
                        i += 1
                        continue

                    h = max(40, bounds["h"])
                    clip_h = min(h, MAX_CLIP_H)
                    no_split = title.startswith("各阶段") or title.startswith("语音")
                    if no_split:
                        clip_h = h

                    if bounds["secW"] > 0:
                        clip_w = int(min(VIEWPORT_W, max(640, bounds["secW"] + 24)))
                    else:
                        clip_w = VIEWPORT_W

                    png = await api_render.capture_region(page, bounds["y"], int(clip_h), clip_w)
                    if png:
                        sections.append(SectionImage(title=title, png_bytes=png))

                    if not no_split and h > clip_h:
                        remaining = h - clip_h
                        offset_y = bounds["y"] + clip_h
                        while remaining > 0:
                            part_h = min(remaining, MAX_CLIP_H)
                            png = await api_render.capture_region(page, offset_y, int(part_h), clip_w)
                            if not png:
                                break
                            sections.append(SectionImage(title=f"{title}(续)", png_bytes=png))
                            remaining -= part_h
                            offset_y += part_h

                i += 1

            if not sections:
                png = await page.screenshot(type="png", full_page=True)
                return [SectionImage(title="从者页面", png_bytes=png)]

            return sections

        finally:
            await page.close()

    except Exception as e:
        print(f"[wiki_screenshot] 截图异常: {type(e).__name__}: {e}")
        traceback.print_exc()
        return []


async def capture_servant_page(cn_name: str, *, timeout_ms: int = 20000) -> bytes | None:
    sections = await capture_servant_sections(cn_name, timeout_ms=timeout_ms)
    return sections[0].png_bytes if sections else None


async def close_browser():
    await api_render.close_browser()
