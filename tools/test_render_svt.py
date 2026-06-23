#!/usr/bin/env python3
"""
离线渲染测试脚本：从 svt2.json 生成从者信息图并保存为 PNG。

用法（在仓库根目录执行）：
    python tools/test_render_svt.py

输出：
    tools/svt_table.png
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# 将仓库根目录加入 sys.path，使相对导入可被正常解析
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from plugins.fgo.render.svt_mooncell import render_svt_base_table  # noqa: E402


async def main() -> None:
    fixture = Path(__file__).parent / "svt2.json"
    if not fixture.exists():
        print(f"[ERROR] 测试数据文件不存在: {fixture}", file=sys.stderr)
        sys.exit(1)

    detail = json.loads(fixture.read_text(encoding="utf-8"))

    print("正在渲染…")
    png = await render_svt_base_table(detail)

    out = Path(__file__).parent / "svt_table.png"
    out.write_bytes(png)
    print(f"渲染完成 -> {out}  ({len(png):,} bytes)")


if __name__ == "__main__":
    asyncio.run(main())
