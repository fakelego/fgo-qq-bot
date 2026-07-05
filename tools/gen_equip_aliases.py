"""
从 Atlas Academy 数据生成 equip_cn.yaml（礼装别名表）

数据源:
1. Atlas JP export (2611 礼装) — id, collectionNo, name, ruby
2. Atlas CN export (2270 礼装) — 中文 name
3. 已有 equip_cn.yaml — 保留手动维护的昵称/别名

输出: plugins/fgo/data/aliases/equip_cn.yaml
"""
from __future__ import annotations

import json
import sys
import urllib.request
from collections import OrderedDict
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
OUTPUT_PATH = ROOT / "plugins" / "fgo" / "data" / "aliases" / "equip_cn.yaml"
EXISTING_PATH = OUTPUT_PATH

ATLAS_JP_URL = "https://api.atlasacademy.io/export/JP/nice_equip.json"
ATLAS_CN_URL = "https://api.atlasacademy.io/export/CN/nice_equip.json"

# 礼装类型标记
FLAG_NAMES = {
    "svtEquipFriendShip": "牵绊礼装",
    "svtEquipValentine": "情人节礼装",
    "svtEquipChocolate": "巧克力礼装",
    "svtEquipEventReward": "活动奖励",
    "svtEquipEventPointReward": "活动点数奖励",
    "svtEquipCampaign": "限时活动",
    "svtEquipShop": "商店兑换",
}


def load_json_url(url: str) -> list[dict]:
    print(f"  下载: {url}")
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_existing_aliases() -> dict[int, dict]:
    if not EXISTING_PATH.exists():
        return {}
    data = yaml.safe_load(EXISTING_PATH.read_text(encoding="utf-8")) or {}
    equips = data.get("equips", {})
    result = {}
    if isinstance(equips, dict):
        for display_name, info in equips.items():
            if not isinstance(info, dict):
                continue
            try:
                atlas_id = int(info.get("atlas_id", 0))
            except (ValueError, TypeError):
                continue
            if atlas_id > 0:
                result[atlas_id] = {
                    "display_name": display_name,
                    "aliases": info.get("aliases", []),
                    "collection_no": info.get("collection_no"),
                }
    return result


def normalize(s: str) -> str:
    return " ".join(str(s).strip().split())


def generate_basic_aliases(cn_name: str, jp_name: str, ruby: str, bond_owner: str | None) -> list[str]:
    aliases = []
    seen = set()

    def add(s: str):
        s = normalize(s)
        if s and s not in seen:
            aliases.append(s)
            seen.add(s)

    add(cn_name)
    if jp_name and jp_name != cn_name:
        add(jp_name)
    if ruby and ruby != jp_name and ruby != cn_name:
        add(ruby)
    if bond_owner:
        add(bond_owner)

    return aliases


def main():
    print("=== 从 Atlas Academy 生成礼装别名表 ===\n")

    # 1. 下载数据
    print("[1/3] 下载 Atlas 数据...")
    jp_equips = load_json_url(ATLAS_JP_URL)
    cn_equips = load_json_url(ATLAS_CN_URL)
    print(f"  JP: {len(jp_equips)} 礼装, CN: {len(cn_equips)} 礼装")

    # 2. CN 名字映射
    print("\n[2/3] 建立中文名索引...")
    cn_name_map: dict[int, str] = {}
    for eq in cn_equips:
        sid = eq.get("id")
        if sid:
            cn_name_map[sid] = eq.get("name", "")
    print(f"  CN 名字映射: {len(cn_name_map)} 条")

    # 加载已有别名
    existing = load_existing_aliases()
    print(f"  已有别名: {len(existing)} 条")

    # 3. 生成
    print("\n[3/3] 生成礼装别名表...")

    entries = []
    skipped = 0

    # 先收集所有礼装，建立 bond_owner 映射
    # 牵绊礼装的 bondEquipOwner 是关联从者的 atlas_id，后面再补名字
    for eq in jp_equips:
        sid = eq.get("id")
        if not sid:
            continue

        cno = eq.get("collectionNo")
        jp_name = eq.get("name", "")
        ruby = eq.get("ruby", "")
        rarity = eq.get("rarity", 0)
        flag = eq.get("flag", "")

        # CN 名
        cn_name = cn_name_map.get(sid, "")
        if not cn_name:
            cn_name = eq.get("originalName", jp_name)

        # display_name
        old = existing.get(sid)
        display_name = (old.get("display_name") if old else "") or cn_name or jp_name

        if not display_name:
            skipped += 1
            continue

        # 基础别名
        bond_owner = None  # 可后续从 servant 表关联
        basic = generate_basic_aliases(display_name, jp_name, ruby, bond_owner)

        # 合并旧别名
        old_aliases = old.get("aliases", []) if old else []
        merged = basic.copy()
        for a in old_aliases:
            a = normalize(a)
            if a and a not in merged:
                merged.append(a)

        entries.append({
            "display_name": display_name,
            "atlas_id": sid,
            "collection_no": cno,
            "rarity": rarity,
            "aliases": merged,
        })

    # 按 collection_no 排序
    entries.sort(key=lambda x: (x["collection_no"] or 99999, x["display_name"]))

    # 处理重名
    from collections import Counter
    name_counts = Counter(e["display_name"] for e in entries)
    name_seen: dict[str, int] = {}
    for entry in entries:
        dn = entry["display_name"]
        if name_counts[dn] > 1:
            name_seen[dn] = name_seen.get(dn, 0) + 1
            if name_seen[dn] > 1:
                new_dn = f"{dn}（No.{entry['collection_no']}）"
                norm_dn = dn.strip().lower()
                entry["aliases"] = [a for a in entry["aliases"] if a.strip().lower() != norm_dn]
                if new_dn not in entry["aliases"]:
                    entry["aliases"].insert(0, new_dn)
                entry["display_name"] = new_dn

    # 构建 YAML
    equips_dict = OrderedDict()
    for entry in entries:
        equips_dict[entry["display_name"]] = OrderedDict([
            ("atlas_id", entry["atlas_id"]),
            ("collection_no", entry["collection_no"]),
            ("aliases", entry["aliases"]),
        ])

    output = {"equips": equips_dict}

    class OrderedDumper(yaml.SafeDumper):
        pass

    def _dict_representer(dumper, data):
        return dumper.represent_mapping(
            yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
            data.items()
        )
    OrderedDumper.add_representer(OrderedDict, _dict_representer)

    yaml_text = yaml.dump(
        output,
        Dumper=OrderedDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=200,
    )
    OUTPUT_PATH.write_text(yaml_text, encoding="utf-8")

    print(f"\n=== 完成 ===")
    print(f"  输出礼装数: {len(entries)}")
    print(f"  跳过（无名称）: {skipped}")
    print(f"  输出文件: {OUTPUT_PATH}")

    # 统计
    existing_ids = set(existing.keys())
    new_ids = {e["atlas_id"] for e in entries}
    added = new_ids - existing_ids
    if added:
        print(f"  新增: {len(added)} 礼装")

    cnos = [e["collection_no"] for e in entries if e["collection_no"] is not None]
    if cnos:
        print(f"  collection_no 范围: {min(cnos)} ~ {max(cnos)}")
    print("\n完成！")


if __name__ == "__main__":
    main()
