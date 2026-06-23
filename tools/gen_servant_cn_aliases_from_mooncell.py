import asyncio
import json
import re
from pathlib import Path

import aiohttp
import yaml

MOONCELL_API = "https://fgo.wiki/api.php"
PAGE_TITLE = "英灵图鉴/数据"
ATLAS_BASE = "https://api.atlasacademy.io"

OUT_PATH = Path("plugins/fgo/data/aliases/servant_cn.yaml").resolve()
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

MAP_CACHE = Path("tools/atlas_collection_map.json")

# 关键：Mooncell 页面源文本里记录不一定“按行 id=...”，所以用跨行 finditer 抓取每条记录
ITEM_RE = re.compile(
    r"id=(?P<id>\d+)\s+"
    r"name_cn=(?P<name_cn>.*?)\s+"
    r"name_jp=(?P<name_jp>.*?)\s+"
    r"name_en=(?P<name_en>.*?)\s+"
    r"name_link=(?P<name_link>.*?)\s+"
    r"name_other=(?P<name_other>.*?)\s+"
    r"method=(?P<method>.*?)\s+"
    r"tag=(?P<tag>.*?)(?=\s+id=\d+\s+name_cn=|$)",
    flags=re.S,
)


def split_other(s: str) -> list[str]:
    s = (s or "").strip()
    if not s:
        return []
    # Mooncell 这页目前用 & 分隔多个别名
    return [p.strip() for p in s.split("&") if p.strip()]


def uniq(seq: list[str]) -> list[str]:
    seen = set()
    out = []
    for x in seq:
        x = (x or "").strip()
        if not x:
            continue
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


async def mw_get_wikitext(session: aiohttp.ClientSession, title: str) -> str:
    params = {
        "action": "query",
        "format": "json",
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "titles": title,
        "formatversion": "2",
    }
    async with session.get(MOONCELL_API, params=params) as resp:
        resp.raise_for_status()
        data = await resp.json()

    pages = data.get("query", {}).get("pages", [])
    if not pages:
        raise RuntimeError("Mooncell API: query.pages is empty")

    page0 = pages[0]
    revs = page0.get("revisions")
    if not revs:
        raise RuntimeError(f"Mooncell API: no revisions for title={title}. keys={list(page0.keys())}")

    r0 = revs[0]
    if "slots" in r0 and "main" in r0["slots"] and "content" in r0["slots"]["main"]:
        return r0["slots"]["main"]["content"]
    if "*" in r0:
        return r0["*"]

    raise RuntimeError(f"Mooncell API: cannot find wikitext content. revision keys={list(r0.keys())}")


async def atlas_get_atlas_id_by_collection_no(session: aiohttp.ClientSession, cno: int) -> int | None:
    # 注意：该接口不支持 HEAD，只支持 GET
    url = f"{ATLAS_BASE}/nice/JP/servant/{cno}"
    async with session.get(url) as resp:
        if resp.status == 404:
            return None
        resp.raise_for_status()
        data = await resp.json()

    sid = data.get("id")

    # 双保险校验：确认返回的 collectionNo 真的等于我们请求的 cno
    ret_cno = data.get("collectionNo")
    if ret_cno is not None:
        try:
            if int(ret_cno) != int(cno):
                print(f"[gen] WARN atlas collectionNo mismatch: req={cno} got={ret_cno} id={sid}")
        except Exception:
            pass

    return int(sid) if sid is not None else None


async def atlas_collection_to_id_via_individual_fetch(
    session: aiohttp.ClientSession,
    collection_nos: list[int],
    concurrency: int = 8,
) -> dict[int, int]:
    # 读缓存
    if MAP_CACHE.exists():
        cache = json.loads(MAP_CACHE.read_text(encoding="utf-8"))
        m = {int(k): int(v) for k, v in cache.items()}
    else:
        m = {}

    sem = asyncio.Semaphore(concurrency)

    async def worker(cno: int):
        if cno in m:
            return
        async with sem:
            sid = await atlas_get_atlas_id_by_collection_no(session, cno)
            if sid is not None:
                m[cno] = sid
            else:
                print(f"[gen] atlas miss collectionNo={cno}")

    await asyncio.gather(*(worker(cno) for cno in collection_nos))

    MAP_CACHE.parent.mkdir(parents=True, exist_ok=True)
    MAP_CACHE.write_text(
        json.dumps({str(k): v for k, v in sorted(m.items())}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[gen] saved atlas map cache: {MAP_CACHE.resolve()} size={len(m)}")
    return m


async def main():
    print(f"[gen] OUT_PATH = {OUT_PATH}")

    timeout = aiohttp.ClientTimeout(total=180)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        print("[gen] fetching mooncell wikitext...")
        text = await mw_get_wikitext(session, PAGE_TITLE)
        print(f"[gen] mooncell text len={len(text)}")

        items = list(ITEM_RE.finditer(text))
        print(f"[gen] parsed mooncell items={len(items)}")

        if items:
            mm = items[0]
            print("[gen] sample:", mm.group("id"), mm.group("name_cn"), (mm.group("name_other") or "")[:30])

        collection_nos = sorted({int(m.group("id")) for m in items})
        print(f"[gen] unique collection_nos={len(collection_nos)}")

        print("[gen] building collectionNo -> atlas_id map (individual fetch)...")
        cno_to_atlas = await atlas_collection_to_id_via_individual_fetch(session, collection_nos, concurrency=8)

        servants: dict[str, dict] = {}
        written = 0

        for m in items:
            cno = int(m.group("id"))
            name_cn = m.group("name_cn").strip()
            name_jp = m.group("name_jp").strip()
            name_en = m.group("name_en").strip()
            name_other = m.group("name_other").strip()

            atlas_id = cno_to_atlas.get(cno, -1)
            if atlas_id <= 0:
                continue

            aliases = uniq([name_cn, name_jp, name_en] + split_other(name_other))
            display = name_cn or name_en or name_jp or f"collectionNo:{cno}"

            servants[display] = {
                "atlas_id": int(atlas_id),
                "collection_no": int(cno),
                "aliases": aliases,
            }
            written += 1

        out = {"servants": servants}
        OUT_PATH.write_text(yaml.safe_dump(out, allow_unicode=True, sort_keys=False), encoding="utf-8")
        print(f"[gen] done. written servants={written} -> {OUT_PATH}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        import traceback

        print("[gen] FAILED:", type(e).__name__, e)
        traceback.print_exc()
        raise