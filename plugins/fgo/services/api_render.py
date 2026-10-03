"""fgowiki API 渲染引擎(核心)

「parse API 获取 HTML → 本地渲染」管线的共享实现:
- parse API 拿页面 HTML(磁盘缓存 7 天,未命中时用搜索 API 兜底标题)
- CSS 一次收集 + 磁盘缓存(含 Font Awesome 字体 base64 内嵌,绕开跨域 CORS)
- 图片按 URL SHA1 磁盘缓存,渲染时路由拦截直接 fulfill,重复查询零图片请求
- 渲染页统一清洗:隐藏 [编辑]/tabber 标签栏/阶段选择器,展开 tabber 面板,
  删除无关提示栏,重置为侧边栏让位的 margin

目标:把对 fgo.wiki 的访问降到最低,同时渲染效果与原网页截图一致。
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import re
import time
from pathlib import Path
from urllib.parse import quote, urljoin

import aiohttp
from aiohttp.resolver import ThreadedResolver
from playwright.async_api import Browser, Page, async_playwright

_browser: Browser | None = None
_browser_lock = asyncio.Lock()

DATA_DIR = Path(__file__).parent.parent / "data"
CACHE_DIR = DATA_DIR / "cache"
CSS_CACHE = CACHE_DIR / "fgowiki.css"
PAGE_CACHE_DIR = CACHE_DIR / "pages"
IMG_CACHE_DIR = CACHE_DIR / "img"

CSS_TTL = 30 * 86400      # CSS 缓存 30 天
PAGE_TTL = 7 * 86400      # 页面 HTML 缓存 7 天

# 收集 CSS 用的页面(皮肤级样式各页一致,取从者页即可)
CSS_COLLECT_URL = "https://fgo.wiki/w/%E6%91%A9%E6%A0%B9"

_IMG_CT = {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "gif": "image/gif", "webp": "image/webp", "svg": "image/svg+xml",
}


def _session(**kw) -> aiohttp.ClientSession:
    """创建带系统 DNS(ThreadedResolver)的 aiohttp 会话。

    aiodns 在部分环境(尤其 Windows)下解析不稳定,统一走线程解析器。
    """
    return aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=kw.pop("total", 30)),
        connector=aiohttp.TCPConnector(resolver=ThreadedResolver()),
        **kw,
    )

# 渲染页统一清洗样式(原网页截图时代的隐藏规则 + API 渲染特有规则)
CLEANUP_CSS = """
.tabber__panel, [role='tabpanel'], .tabber__section {
    display: block !important; position: static !important; }
#content, .mw-body, #mw-content-text, .mw-body-content, .mw-parser-output {
    margin-left: 0 !important; margin-right: 0 !important;
    padding-left: 0 !important; padding-right: 0 !important; }
table { margin-left: 0 !important; margin-right: 0 !important; }
.mw-editsection, .editsection { display: none !important; }
.tabber__header { display: none !important; }
.graphpicker-prev, .graphpicker-next, .graphpicker-select { display: none !important; }
#mw-navigation, #mw-panel, #p-logo, #column-one, .mw-sidebar, .sidebar,
#siteNotice, #mw-head, #mw-page-base, #footer-places, #footer-icons,
#footer-info, #catlinks, iframe, [id*="google_ads"], [class*="adsbygoogle"],
.mw-dialog, [role="dialog"] { display: none !important; }
"""

# 删除「如需了解宝具动画 / 宝具背景音乐」提示栏:
# 定位特征 = 绿底 style(#F9FFEA) + 文本含关键词
REMOVE_NOTICE_JS = """() => {
    const KW = ['宝具动画', '宝具背景音乐'];
    const hit = (s) => KW.some(k => s.includes(k));
    const divs = Array.from(document.querySelectorAll('div'));
    for (const d of divs) {
        const st = d.getAttribute('style') || '';
        if (!st.includes('#F9FFEA')) continue;
        const t = d.textContent || '';
        if (!hit(t)) continue;
        const parent = d.parentElement;
        d.remove();
        let p = parent;
        while (p && p !== document.body && !p.textContent.trim() && p.children.length === 0) {
            const pp = p.parentElement;
            p.remove();
            p = pp;
        }
    }
}"""

# 表格「需求宽度」测量:px 定宽直接取;有 max-width 取 max-width;
# 纯百分比宽(自适应视口)的不参与
WIDTH_JS = """(els) => {
    let maxW = 0;
    for (const t of els) {
        const cs = getComputedStyle(t);
        if (cs.display === 'none' || cs.visibility === 'hidden') continue;
        let w = 0;
        if (cs.width.endsWith('px')) w = parseFloat(cs.width);
        else if (cs.maxWidth.endsWith('px')) w = parseFloat(cs.maxWidth);
        if (w > maxW) maxW = w;
    }
    return maxW;
}"""


async def get_browser() -> Browser:
    global _browser
    async with _browser_lock:
        if _browser is None or not _browser.is_connected():
            pw = await async_playwright().start()
            _browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
            )
        return _browser


async def close_browser() -> None:
    global _browser
    if _browser and _browser.is_connected():
        await _browser.close()
        _browser = None


# ─────────────────────────── CSS 收集与缓存 ───────────────────────────

def _fix_css_urls(css_text: str, base_url: str) -> str:
    """把 CSS 里的相对 url()(含 //、/、../)按来源 URL 解析为绝对地址,保持原引号配对。"""

    def repl(m):
        quote_ = m.group(1) or ""
        path = m.group(2).strip()
        if path.startswith(("http:", "https:", "data:", "//")):
            return m.group(0)
        return f"url({quote_}{urljoin(base_url, path)}{quote_})"

    return re.sub(r"url\(\s*([\'\"])?([^)'\"]+)\1?\s*\)", repl, css_text, flags=re.I)


async def _inline_fonts(css: str, session: aiohttp.ClientSession) -> str:
    """把 Font Awesome 字体下载后 base64 内嵌进 @font-face。

    跨域字体受 CORS 校验,本地渲染页面(Origin=null)加载必然失败;
    内嵌后零外链、零 CORS 问题,还减少对静态站的重复请求。
    """

    async def download(url: str):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status == 200:
                    return await r.read()
        except Exception:
            pass
        return None

    for m in list(re.finditer(r"@font-face\s*\{[^}]*\}", css)):
        face = m.group(0)
        if "Awesome" not in face:
            continue
        fonts = re.findall(r"url\(\s*([^)]+\.(?:woff2|woff|ttf|eot)[^)]*)\)", face, re.I)
        if not fonts:
            continue
        # 按 Chromium 支持优先级选格式:woff2 > woff > ttf > eot
        order = {"woff2": 0, "woff": 1, "ttf": 2, "eot": 3}
        fonts.sort(key=lambda u: order.get(u.strip().lower().rsplit(".", 1)[-1], 9))
        data = fmt = None
        for url in fonts:
            b = await download(url.strip().strip("'\""))
            if b is not None:
                data, fmt = b, url.strip().lower().split("#")[0].rsplit(".", 1)[-1]
                break
        if data is None:
            continue
        mime = {
            "woff2": "font/woff2", "woff": "font/woff",
            "ttf": "font/ttf", "eot": "application/vnd.ms-fontobject",
        }[fmt]
        b64 = base64.b64encode(data).decode()
        new_src = f'src:url("data:{mime};base64,{b64}") format(\'{fmt}\');'
        # 删除 face 里全部 src 声明(可能有多个,且有的结尾无分号),再插入 data URI
        face_new = re.sub(r"src:[^;]+;", "", face, flags=re.I)
        face_new = re.sub(r"src:[^;}]+", "", face_new, flags=re.I)
        face_new = face_new.rstrip()[:-1] + new_src + "}"
        css = css.replace(face, face_new, 1)
    return css


async def _collect_css() -> str:
    """打开 fgo.wiki 页面收集完整 CSS:<link rel=stylesheet> 原始内容 + inline <style>。"""
    browser = await get_browser()
    page: Page = await browser.new_page(viewport={"width": 1100, "height": 1200})
    try:
        await page.goto(CSS_COLLECT_URL, wait_until="load", timeout=30000)
        await asyncio.sleep(3)  # 等 ResourceLoader 注入全部 inline style
        collected = await page.evaluate("""() => {
            const hrefs = Array.from(document.querySelectorAll('link[rel=stylesheet]'))
                .map(l => l.href).filter(h => h && !h.startsWith('data:'));
            const inline = Array.from(document.querySelectorAll('style'))
                .map(s => s.textContent).join('\\n');
            return {hrefs: hrefs, inline: inline};
        }""")
    finally:
        await page.close()

    css_parts = [_fix_css_urls(collected["inline"], CSS_COLLECT_URL)]
    async with _session() as s:
        for href in collected["hrefs"]:
            try:
                async with s.get(href, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status == 200:
                        css_parts.append(_fix_css_urls(await r.text(), href))
            except Exception:
                pass
        css = "\n".join(css_parts)
        css = await _inline_fonts(css, s)
    return css


async def ensure_css() -> str | None:
    """返回站点 CSS(缓存 30 天)。收集失败返回 None。"""
    CSS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    try:
        if CSS_CACHE.exists() and CSS_CACHE.stat().st_size > 100_000:
            if time.time() - CSS_CACHE.stat().st_mtime < CSS_TTL:
                return CSS_CACHE.read_text(encoding="utf-8")
    except OSError:
        pass
    try:
        css = await _collect_css()
    except Exception as e:
        print(f"[api_render] CSS 收集失败: {type(e).__name__}: {e}")
        return None
    if len(css) < 50_000:
        print(f"[api_render] CSS 异常偏小({len(css)} 字符),放弃缓存")
        return css
    try:
        CSS_CACHE.write_text(css, encoding="utf-8")
    except OSError:
        pass
    return css


# ─────────────────────────── 页面 HTML 获取与缓存 ───────────────────────────

# 国服职阶简称 → 英文职阶(fgowiki 变体页面括号内用英文/日文职阶)
_CN_CLASS_MAP = {
    "剑阶": "saber", "弓阶": "archer", "枪阶": "lancer", "骑阶": "rider",
    "术阶": "caster", "杀阶": "assassin", "狂阶": "berserker", "盾阶": "shielder",
    "裁阶": "ruler", "仇阶": "avenger", "他阶": "alterego",
    "月癌": "mooncancer", "月之癌": "mooncancer",
    "降临者": "foreigner", "伪装者": "pretender",
}


def _normalize_name(name: str) -> str:
    """全角括号 → 半角(MediaWiki 页面名用半角括号)。"""
    return (
        name.replace("（", "(").replace("）", ")")
        .replace("〔", "(").replace("〕", ")")
        .replace("［", "(").replace("］", ")")
    )


def _pick_title(name: str, candidates: list[str]) -> str | None:
    """从候选中挑最可能的规范页面名(候选来自 prefixsearch/搜索,已排除子页面)。"""
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    # 查询名括号里的职阶 → 英文职阶,用于匹配变体页面
    m = re.search(r"[（(〔\[［]([^)）〕\]］]*)[)）〕\]］]", name)
    q_paren = m.group(1).strip() if m else ""
    cls_en = _CN_CLASS_MAP.get(q_paren)
    if cls_en is None and q_paren and q_paren.lower() in _CN_CLASS_MAP.values():
        cls_en = q_paren.lower()

    def paren_of(t: str) -> str:
        m2 = re.search(r"[（(〔\[［]([^)）〕\]］]*)[)）〕\]］]", t)
        return m2.group(1).strip().lower() if m2 else ""

    base = re.sub(r"[（(〔\[［][^)）〕\]］]*[)）〕\]］]\s*$", "", name).strip()

    if cls_en:
        for c in candidates:
            if cls_en in paren_of(c):
                return c
    if q_paren:
        for c in candidates:
            if paren_of(c):
                return c
    for c in candidates:
        if c == base:
            return c
    return candidates[0]


async def _resolve_title(name: str) -> str | None:
    """页面名不精确时兜底:prefixsearch(前缀)优先,再退全站搜索。

    候选排除子页面(/相关礼装 等),按职阶/括号/基础名评分挑主页面。
    """
    norm = _normalize_name(name)
    base = re.sub(r"\([^)]*\)\s*$", "", norm).strip() or norm

    async with _session() as s:
        candidates: list[str] = []
        seen: set[str] = set()

        async def prefix_search(q: str) -> list[str]:
            try:
                async with s.get("https://fgo.wiki/api.php", params={
                    "action": "query", "list": "prefixsearch", "pssearch": q,
                    "pslimit": 10, "format": "json",
                }) as r:
                    data = await r.json()
                return [p["title"] for p in data.get("query", {}).get("prefixsearch", [])]
            except Exception:
                return []

        async def full_search(q: str) -> list[str]:
            try:
                async with s.get("https://fgo.wiki/api.php", params={
                    "action": "query", "list": "search", "srsearch": q,
                    "srlimit": 10, "format": "json",
                }) as r:
                    data = await r.json()
                return [h["title"] for h in data.get("query", {}).get("search", [])]
            except Exception:
                return []

        for q in dict.fromkeys([norm, base]):
            for t in await prefix_search(q):
                if "/" not in t and t not in seen:
                    seen.add(t)
                    candidates.append(t)
        if not candidates:
            for q in dict.fromkeys([base, norm]):
                for t in await full_search(q):
                    if "/" not in t and t not in seen:
                        seen.add(t)
                        candidates.append(t)
        return _pick_title(name, candidates)


async def _parse_html(name: str) -> str | None:
    """parse API 拿页面 HTML;页面名不精确时先规范化括号再解析,仍失败走搜索兜底。"""
    async with _session() as s:
        for page_name in dict.fromkeys([name, _normalize_name(name)]):
            async with s.get("https://fgo.wiki/api.php", params={
                "action": "parse", "page": page_name, "prop": "text", "format": "json",
            }) as r:
                data = await r.json()
            if "error" not in data and "parse" in data:
                return data["parse"]["text"]["*"]

        # 页面名不精确:搜索解析规范标题
        title = await _resolve_title(name)
        if not title:
            return None
        async with s.get("https://fgo.wiki/api.php", params={
            "action": "parse", "page": title, "prop": "text", "format": "json",
        }) as r:
            data = await r.json()
        if "error" not in data and "parse" in data:
            return data["parse"]["text"]["*"]
        return None


async def fetch_page_html(name: str) -> str | None:
    """获取页面 HTML(磁盘缓存 7 天)。失败返回 None。"""
    PAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = PAGE_CACHE_DIR / f"{quote(name, safe='')}.html"
    try:
        if cache_file.exists() and cache_file.stat().st_size > 10_000:
            if time.time() - cache_file.stat().st_mtime < PAGE_TTL:
                return cache_file.read_text(encoding="utf-8")
    except OSError:
        pass
    try:
        html = await _parse_html(name)
    except Exception as e:
        print(f"[api_render] parse 获取 {name} 失败: {type(e).__name__}: {e}")
        return None
    if not html:
        return None
    try:
        cache_file.write_text(html, encoding="utf-8")
    except OSError:
        pass
    return html


def prepare_html(html: str) -> str:
    """HTML 预处理:
    - 协议相对 URL(//media...)在本地页面解析失败 → 补全为 https
    - 取消懒加载:懒加载图片滚动后才下载,会导致布局变化、底部内容被挤出截图
    """
    html = html.replace('src="//', 'src="https://')
    html = html.replace('srcset="//', 'srcset="https://')
    html = html.replace('loading="lazy"', 'loading="eager"')
    return html


# ─────────────────────────── 本地渲染管线 ───────────────────────────

async def _image_route(route, request) -> None:
    """图片路由:磁盘缓存命中直接 fulfill,未命中 fetch 后落盘。"""
    url = request.url
    try:
        path = url.split("?")[0]
        ext = path.rsplit(".", 1)[-1].lower()
        if ext not in _IMG_CT:
            ext = "img"
        key = hashlib.sha1(url.encode("utf-8")).hexdigest()
        cache_file = IMG_CACHE_DIR / f"{key}.{ext}"
        if cache_file.exists() and cache_file.stat().st_size > 0:
            await route.fulfill(path=str(cache_file), content_type=_IMG_CT.get(ext, "application/octet-stream"))
            return
        resp = await route.fetch()
        body = await resp.body()
        try:
            IMG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_file.write_bytes(body)
        except OSError:
            pass
        # route.fetch 返回的是解码后的 body,转发时去掉编码/长度头避免双重解压
        headers = {
            k: v for k, v in resp.headers.items()
            if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")
        }
        await route.fulfill(status=resp.status, headers=headers, body=body)
    except Exception:
        try:
            await route.continue_()
        except Exception:
            pass


async def render_page(
    html: str,
    *,
    viewport_w: int = 1100,
    viewport_h: int = 1200,
    image_timeout: int = 60,
) -> Page | None:
    """本地渲染页面:注入缓存 CSS、清洗页面、等待图片。失败返回 None。"""
    css = await ensure_css()
    if css is None:
        return None
    browser = await get_browser()
    page: Page = await browser.new_page(
        viewport={"width": viewport_w, "height": viewport_h}, device_scale_factor=1
    )
    await page.route("https://media.fgo.wiki/**", _image_route)

    full_html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<base href='https://fgo.wiki/'>"
        f"<style>{css}</style>"
        "</head><body>"
        "<div id='content' class='mw-body'>"
        "<div id='mw-content-text' class='mw-body-content'>"
        f"{prepare_html(html)}"
        "</div></div></body></html>"
    )
    await page.set_content(full_html, wait_until="domcontentloaded")
    await page.add_style_tag(content=CLEANUP_CSS)
    await page.evaluate(REMOVE_NOTICE_JS)
    # 关闭可能的浮动弹窗(不碰内容区元素)
    try:
        await page.evaluate(
            """() => { document.querySelectorAll('.mw-dialog,[role="dialog"]').forEach(e => e.remove()); }"""
        )
    except Exception:
        pass

    # 等全部图片(naturalWidth > 0 才算真加载出来,加载失败的不计入)
    try:
        await page.wait_for_function(
            """() => {
                const imgs = Array.from(document.querySelectorAll('img')).filter(i => i.src);
                return imgs.length === 0 || imgs.every(i => i.complete && i.naturalWidth > 0);
            }""",
            timeout=image_timeout * 1000,
        )
    except Exception:
        pending = await page.evaluate(
            """() => Array.from(document.querySelectorAll('img'))
                       .filter(i => i.src && (!i.complete || !i.naturalWidth)).length"""
        )
        print(f"[api_render] {pending} 张图片未在超时内加载完,继续")
    return page


async def capture_region(page: Page, y: float, height: int, width: int) -> bytes | None:
    """滚动到文档坐标 y,截取该区域 [y, y+height),返回 PNG bytes。

    截图前把视口加高到能容纳目标区域(最高 16000px);页面总高不足时
    滚动会被钳制,此时按实际滚动位置换算截取起点。宽度保持 page 当前值,
    clip 宽度不超过视口宽度。
    """
    vp = page.viewport_size or {"width": 1100, "height": 1200}
    vp_w, vp_h = vp["width"], int(min(max(vp["height"], height + 100), 16000))
    if vp_h != vp["height"]:
        await page.set_viewport_size({"width": vp_w, "height": vp_h})
    await page.evaluate("(y) => window.scrollTo(0, Math.max(0, y))", y)
    await asyncio.sleep(0.15)
    top = await page.evaluate("(y) => Math.max(0, y - window.scrollY)", y)
    top = int(min(top, vp_h - 10))
    clip_h = int(min(height, vp_h - top))
    try:
        return await page.screenshot(
            type="png",
            clip={"x": 0, "y": top, "width": int(min(width, vp_w)), "height": clip_h},
        )
    except Exception:
        return None
