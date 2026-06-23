# plugins/fgo/services/assets.py
import hashlib
from pathlib import Path
import aiohttp

ASSET_DIR = Path("plugins/fgo/data/cache/assets")
ASSET_DIR.mkdir(parents=True, exist_ok=True)

def _hash_url(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()

async def fetch_image_bytes(session: aiohttp.ClientSession, url: str) -> bytes:
    fn = ASSET_DIR / f"{_hash_url(url)}.img"
    if fn.exists() and fn.stat().st_size > 0:
        return fn.read_bytes()

    async with session.get(url) as resp:
        resp.raise_for_status()
        data = await resp.read()

    fn.write_bytes(data)
    return data