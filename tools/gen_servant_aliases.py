"""
从 Atlas Academy 数据重新生成 servant_cn.yaml

数据源:
1. Atlas JP export (474 从者) — id, collectionNo, ruby, className
2. Atlas CN export (443 从者) — 中文 name
3. 现有 servant_cn.yaml — 保留手动维护的昵称/别名

输出: plugins/fgo/data/aliases/servant_cn.yaml
"""
from __future__ import annotations

import json
import sys
import urllib.request
from collections import OrderedDict
from pathlib import Path

import yaml

# ─── 配置 ─────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
OUTPUT_PATH = ROOT / "plugins" / "fgo" / "data" / "aliases" / "servant_cn.yaml"
EXISTING_PATH = ROOT / "plugins" / "fgo" / "data" / "aliases" / "servant_cn.yaml"

ATLAS_JP_URL = "https://api.atlasacademy.io/export/JP/nice_servant.json"
ATLAS_CN_URL = "https://api.atlasacademy.io/export/CN/nice_servant.json"

# 职阶中文名
CLASS_CN_MAP = {
    "saber": "剑阶", "archer": "弓阶", "lancer": "枪阶",
    "rider": "骑阶", "caster": "术阶", "assassin": "杀阶",
    "berserker": "狂阶", "ruler": "裁阶", "avenger": "仇阶",
    "alterEgo": "分身", "moonCancer": "月癌", "foreigner": "异界",
    "pretender": "伪阶", "shielder": "盾阶", "beast": "兽阶",
}

# 属性映射
ATTR_MAP = {
    "earth": "地", "sky": "天", "human": "人", "star": "星", "beast": "兽",
}

# ─── 辅助函数 ─────────────────────────────────────────────────

def load_json_url(url: str) -> list[dict]:
    print(f"  下载: {url}")
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_existing_aliases() -> dict[int, dict]:
    """从现有 servant_cn.yaml 读取，key 为 atlas_id"""
    if not EXISTING_PATH.exists():
        return {}

    data = yaml.safe_load(EXISTING_PATH.read_text(encoding="utf-8")) or {}
    servants = data.get("servants", {})

    result = {}
    if isinstance(servants, dict):
        for display_name, info in servants.items():
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


def normalize_alias(s: str) -> str:
    """规范化单个别名"""
    s = str(s).strip()
    # 去除多余的空白字符
    s = " ".join(s.split())
    return s


def generate_basic_aliases(cn_name: str, jp_name: str, ruby: str, *, include_short: bool = True) -> list[str]:
    """根据中日文名生成基础别名列表

    include_short: 是否生成去括号后的短名。对于本身已带括号（如〔Alter〕）的从者，
                   短名会与基础从者冲突，此时不应生成。
    """
    aliases = []
    seen = set()

    def add(s: str):
        s = normalize_alias(s)
        if s and s not in seen and len(s) > 0:
            aliases.append(s)
            seen.add(s)

    add(cn_name)

    # JP 名 (假名)
    if jp_name and jp_name != cn_name:
        add(jp_name)

    # Ruby (读音)
    if ruby and ruby != jp_name and ruby != cn_name:
        add(ruby)

    # 移除括号后的短名
    # 例如 "阿尔托莉雅·潘德拉贡〔Alter〕" → "阿尔托莉雅·潘德拉贡"
    import re
    short = re.sub(r'[〔（(].*[〕）)]', '', cn_name).strip()
    if include_short and short and short != cn_name:
        add(short)

    return aliases


def merge_aliases(new_aliases: list[str], old_aliases: list[str]) -> list[str]:
    """合并新生成的别名和旧的手动别名"""
    result = []
    seen = set()

    # 新别名在前
    for a in new_aliases:
        a = normalize_alias(a)
        if a and a not in seen:
            result.append(a)
            seen.add(a)

    # 旧别名（手动维护的昵称）补充在后
    for a in (old_aliases or []):
        a = normalize_alias(a)
        if a and a not in seen:
            result.append(a)
            seen.add(a)

    return result


# ─── 主流程 ───────────────────────────────────────────────────

def main():
    print("=== 从 Atlas Academy 重新生成从者别名表 ===\n")

    # 1. 下载 Atlas 数据
    print("[1/4] 下载 Atlas 数据...")
    jp_servants = load_json_url(ATLAS_JP_URL)
    cn_servants = load_json_url(ATLAS_CN_URL)
    print(f"  JP: {len(jp_servants)} 从者, CN: {len(cn_servants)} 从者")

    # 2. 建立 CN 名字查询表 (key=id)
    print("\n[2/4] 建立中文名索引...")
    cn_name_map: dict[int, str] = {}
    cn_original_map: dict[int, str] = {}
    for svt in cn_servants:
        sid = svt.get("id")
        if sid:
            cn_name_map[sid] = svt.get("name", "")
            cn_original_map[sid] = svt.get("originalName", "")
    print(f"  CN 名字映射: {len(cn_name_map)} 条")

    # 3. 加载已有别名
    print("\n[3/4] 加载已有别名表...")
    existing = load_existing_aliases()
    print(f"  已有别名: {len(existing)} 条")

    # 4. 生成新的 servant_cn.yaml
    print("\n[4/4] 生成新别名表...")

    # servers 是列表，由 atlas_id 索引
    servant_entries = []
    skipped = []

    for svt in jp_servants:
        sid = svt.get("id")
        collection_no = svt.get("collectionNo")
        jp_name = svt.get("name", "")
        ruby = svt.get("ruby", "")
        rarity = svt.get("rarity", 0)
        class_name = svt.get("className", "").lower()

        if not sid:
            continue

        # 获取中文名
        cn_name = cn_name_map.get(sid, "")
        if not cn_name:
            # CN 服还没实装，用 JP 名或空
            cn_name = ""

        # 如果 CN 也没有中文名，用 originalName（通常是英文/日文）
        if not cn_name:
            cn_name = svt.get("originalName", jp_name)

        # 确定 display_name
        # 优先用已有文件中的 display_name
        old_entry = existing.get(sid)
        if old_entry and old_entry.get("display_name"):
            display_name = old_entry["display_name"]
        else:
            display_name = cn_name or jp_name

        if not display_name:
            skipped.append(sid)
            continue

        # 生成基础别名（带括号的变体名不生成短名，避免与基础从者冲突）
        import re as _re
        has_bracket = bool(_re.search(r'[〔（(]', display_name))
        basic_aliases = generate_basic_aliases(
            display_name, jp_name, ruby, include_short=not has_bracket
        )

        # 合并旧别名
        old_aliases = old_entry.get("aliases", []) if old_entry else []
        merged = merge_aliases(basic_aliases, old_aliases)

        # 去重：移除与 display_name 完全相同的别名
        merged = [a for a in merged if normalize_alias(a) != normalize_alias(display_name)]

        # 确保 display_name 本身也在 aliases 中（方便搜索到）
        final_aliases = [display_name] + merged

        servant_entries.append({
            "display_name": display_name,
            "atlas_id": sid,
            "collection_no": collection_no,
            "class_name": class_name,
            "aliases": final_aliases,
        })

    # 按 collection_no 排序
    servant_entries.sort(key=lambda x: (x["collection_no"] or 9999, x["display_name"]))

    # 处理重名：为同名从者追加职阶后缀
    # 先统计 display_name 出现次数
    name_counts: dict[str, int] = {}
    for entry in servant_entries:
        dn = entry["display_name"]
        name_counts[dn] = name_counts.get(dn, 0) + 1

    # 对于重名项，用 (职阶) 去重，并从变体中移除基础名别名
    name_seen: dict[str, int] = {}
    for entry in servant_entries:
        dn = entry["display_name"]
        if name_counts[dn] > 1:
            name_seen[dn] = name_seen.get(dn, 0) + 1
            if name_seen[dn] > 1:
                # 后续重名：追加职阶后缀
                class_cn = CLASS_CN_MAP.get(entry.get("class_name", ""), entry.get("class_name", ""))
                new_dn = f"{dn}（{class_cn}）"
                entry["display_name"] = new_dn
                # 从 aliases 中移除基础名（避免搜索时覆盖第一个从者）
                norm_dn = dn.strip().lower()
                entry["aliases"] = [a for a in entry["aliases"] if a.strip().lower() != norm_dn]
                # 确保新名字在 aliases 中
                if new_dn not in entry["aliases"]:
                    entry["aliases"].insert(0, new_dn)
            # 第一个保留原名和原名别名
        else:
            pass  # 不重名，不变

    # 构建 YAML 结构
    servants_dict = OrderedDict()
    for entry in servant_entries:
        key = entry["display_name"]
        servants_dict[key] = OrderedDict([
            ("atlas_id", entry["atlas_id"]),
            ("collection_no", entry["collection_no"]),
            ("aliases", entry["aliases"]),
        ])

    output = {
        "servants": servants_dict,
    }

    # 自定义 YAML 输出（保证格式一致）
    # 使用 PyYAML 的 dump，设置 allow_unicode
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

    # 统计
    print(f"\n=== 完成 ===")
    print(f"  输出从者数: {len(servant_entries)}")
    print(f"  输出文件: {OUTPUT_PATH}")

    # 统计新增/更新
    old_ids = set(existing.keys())
    new_ids = {e["atlas_id"] for e in servant_entries}
    added = new_ids - old_ids
    removed = old_ids - new_ids
    if added:
        added_names = [e["display_name"] for e in servant_entries if e["atlas_id"] in added]
        print(f"  新增 {len(added)} 从者: {added_names[:10]}...")
    if removed:
        removed_names = [existing[rid]["display_name"] for rid in removed if rid in existing]
        print(f"  移除 {len(removed)} 从者（JP已不存在）: {removed_names}")

    # 检查缺失 collection_no
    existing_cnos = {e["collection_no"] for e in servant_entries if e["collection_no"] is not None}
    min_cno = min(existing_cnos)
    max_cno = max(existing_cnos)
    missing_cnos = sorted(set(range(min_cno, max_cno + 1)) - existing_cnos)
    print(f"  collection_no 范围: {min_cno} ~ {max_cno}")
    print(f"  缺失 collection_no: {len(missing_cnos)} 个")

    if skipped:
        print(f"  跳过（无名称）: {len(skipped)} 个 (ids: {skipped[:10]}...)")

    print("\n完成！")


if __name__ == "__main__":
    main()
