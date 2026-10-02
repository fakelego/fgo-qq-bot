# fgo-qq-bot 项目梳理与开发说明

> 最后更新：2026-10-03（对应「Playwright 网页截图」架构）

## 1. 项目概述

`fgo-qq-bot` 是一个基于 **NoneBot2 + OneBot v11** 的 FGO 信息查询 Bot，在 QQ 上提供从者、礼装、素材等信息查询，查询结果以 **fgowiki 网页截图** 的形式返回。

当前仓库地址：

- `fakelego/fgo-qq-bot`

当前项目状态：

- 已完成基础机器人启动链路
- 已完成从者查询体系（11 个查询命令，覆盖基础信息 / 宝具 / 技能 / 资料 / 卡面等）
- 已完成礼装查询体系（别名表 + 网页截图）
- 已完成素材查询体系（道具页面 + 刷取推荐）
- 已完成中文别名系统（从者 / 礼装 / 素材三套 YAML 别名表）
- 已从「PIL 生图」全面转向「Playwright 网页截图」（提交 `170523b 取消生图功能，使用网页截图`）
- 旧 PIL 渲染器与区服偏好存储已废弃（区服功能已移除，见 §8）

---

## 2. 技术栈

### 核心框架
- Python
- NoneBot2（2.5.0）+ nonebot-adapter-onebot（OneBot v11，2.4.6）

### 截图引擎
- Playwright（无头 Chromium，`>=1.48.0`）— 核心展示手段
- Pillow — 仅用于多张 PNG 的垂直拼接

### 数据与网络
- aiohttp — Atlas Academy API 请求
- PyYAML — 别名表加载
- RapidFuzz — 已在依赖中声明，**代码中尚未使用**（预留做模糊匹配）

### 服务与协议
- FastAPI / Uvicorn（NoneBot 运行基础）

---

## 3. 当前仓库结构概览

```text
fgo-qq-bot/
├─ bot.py                          # 启动入口
├─ .env                            # NoneBot 配置（gitignore，含 OneBot 连接信息）
├─ requirements.txt
├─ run_bot.ps1                     # 启动脚本
├─ debug_all_commands.py           # 调试：随机从者/礼装跑全部命令并输出截图
├─ gen_material_aliases.py         # 调试：素材别名生成
├─ scrape_materials.py / _v2.py    # 调试：素材数据抓取
├─ test_card.py / test_card_debug.py
├─ plugins/
│  └─ fgo/
│     ├─ __init__.py               # Bot 环境才加载命令；离线导入不加载
│     ├─ commands/
│     │  ├─ meta/
│     │  │  ├─ ping.py             # /ping
│     │  │  └─ help.py             # /help（内容已过时，待更新）
│     │  └─ query/
│     │     ├─ __init__.py         # 显式 import 各命令模块
│     │     ├─ svt.py              # /查询
│     │     ├─ np.py               # /宝具
│     │     ├─ skill.py            # /技能
│     │     ├─ class_skill.py      # /职阶技能
│     │     ├─ append_skill.py     # /追加技能
│     │     ├─ material.py         # /素材
│     │     ├─ bond.py             # /牵绊
│     │     ├─ profile.py          # /资料、/资料1~/资料6
│     │     ├─ appearance.py       # /形象
│     │     ├─ card.py             # /卡面
│     │     ├─ equip.py            # /礼装
│     │     ├─ item.py             # /道具
│     │     └─ farm.py             # /刷取
│     ├─ services/
│     │  ├─ query/
│     │  │  ├─ servant_helper.py   # 从者查询-截图-筛选公共流水线 fetch()
│     │  │  └─ svt_search.py       # 别名 → Atlas 查询
│     │  ├─ wiki_screenshot.py     # 核心截图引擎（章节切分/tabber/表格截图）
│     │  ├─ wiki_card.py           # 卡面立绘原图提取 + 磁盘缓存
│     │  ├─ wiki_equip_screenshot.py      # 礼装页面截图
│     │  ├─ wiki_material_screenshot.py   # 素材页面 + 掉落关卡截图
│     │  └─ assets.py              # 旧资源缓存（已无调用，可清理）
│     ├─ stores/
│     │  ├─ aliases_servant_cn.py  # 从者别名查找
│     │  ├─ aliases_equip_cn.py    # 礼装别名查找
│     │  ├─ aliases_material_cn.py # 素材别名查找
│     │  └─ atlas_client.py        # Atlas Academy API 客户端
│     ├─ render/                   # 旧 PIL 渲染器（已废弃，无任何引用）
│     │  ├─ svt_card.py
│     │  └─ svt_mooncell.py
│     └─ data/
│        ├─ aliases/
│        │  ├─ servant_cn.yaml     # 从者别名（~3900 行）
│        │  ├─ equip_cn.yaml       # 礼装别名（~17400 行）
│        │  └─ material_cn.yaml    # 素材别名（~790 行）
│        ├─ guides.sample.yaml
│        └─ cache/                 # 卡面图片缓存（gitignore）
└─ tools/
   ├─ gen_servant_cn_aliases_from_mooncell.py
   ├─ gen_servant_aliases.py
   ├─ gen_equip_aliases.py
   ├─ test_render_svt.py
   ├─ atlas_collection_map.json
   └─ svt2.json
```

---

## 4. 已实现的功能命令

### 4.1 Meta 命令

| 命令 | 别名 | 行为 |
|---|---|---|
| `/ping` | — | 返回 `pong` |
| `/help` | `帮助` | 返回帮助文本（**内容过时**，只列了 3 个命令，待更新） |

### 4.2 从者查询命令（走 `servant_helper.fetch()` 公共流水线）

所有从者类命令的链路相同：**关键词 → 从者别名表 → Atlas API → fgowiki 分节截图 → 按标题筛选出目标节**。

| 命令 | 别名 | 返回内容 |
|---|---|---|
| `/查询 摩根` | `svt`、`从者` | 从者页面第一张截图（基础信息） |
| `/宝具 摩根` | `np`、`NP` | 宝具截图；有强化前后多版本时逐条带 `【强化后】` 标签 |
| `/技能 摩根` | `skill` | 主动技能 1/2/3 截图（含强化前后变体，带 `【技能N】` 标签） |
| `/职阶技能 摩根` | `职介技能`、`classskill`、`cs` | 职阶技能截图 |
| `/追加技能 摩根` | `appendskill`、`as` | 追加技能截图（多张表合并为一张） |
| `/素材 摩根` | `材料`、`素材需求`、`material`、`mat` | 灵基再临 / 技能强化素材需求截图 |
| `/牵绊 摩根` | `牵绊点数`、`羁绊`、`bond` | 牵绊点数 / 牵绊礼装截图 |
| `/资料 摩根` | `profile` | 角色详情截图 |
| `/资料1 摩根` ~ `/资料6 摩根` | — | 个人资料 1~6 截图（`profile.py` 循环注册 6 个命令） |
| `/形象 摩根` | `战斗形象`、`立绘`、`appearance`、`skin` | 各阶段图标与战斗形象截图 |
| `/卡面 摩根 3` | `card` | 卡面立绘**原图**（不是截图）；支持阶段 `1-4` 和 `灵衣`，默认阶段 1 |

`/卡面` 特殊之处：不走截图，而是从 fgowiki 页面解析「文件:」链接，按文件名模式匹配阶段（初期/一破/三破/满破/灵衣，另有「从者名+数字」兜底模式，如 `玄奘三藏1.png`），下载原图后按 URL SHA1 缓存在 `plugins/fgo/data/cache/card/`。

### 4.3 礼装与素材命令（独立链路）

| 命令 | 别名 | 返回内容 |
|---|---|---|
| `/礼装 万华镜` | `equip`、`ce`、`礼装查询` | 礼装页面表单区域截图（截到「成长曲线」行为止） |
| `/道具 英雄之证` | `item`、`材料查询`、`道具查询` | 素材页面顶部信息框截图 |
| `/刷取 英雄之证` | `farm`、`掉落`、`刷材料`、`去哪刷` | 「主要掉落关卡」表：自动识别 AP 效率列，按 AP/个 升序只取前 3 行 |

---

## 5. 核心架构

### 5.1 从者查询流水线

```
用户输入 /查询 摩根
  → commands/query/*.py          （NoneBot matcher，解析关键词）
  → services/query/servant_helper.py::fetch()
      1. svt_search.query_svt_detail_by_keyword_cn_first()
           → stores/aliases_servant_cn.py  本地 YAML 别名（精确→包含匹配）
           → stores/atlas_client.py        Atlas Academy API（CN 优先 + JP 成长曲线回退）
      2. wiki_screenshot.capture_servant_sections(cn_name)
           → Playwright 打开 fgo.wiki 页面 → 分节截图
      3. 返回 FetchResult(ok, cn_name, sections)
  → 命令层用 FetchResult.filter() 按标题筛选目标章节
  → MessageSegment.image 发图
```

`FetchResult` 是统一的查询+截图结果容器，`filter()` 支持三种筛选：

- `prefix=` — 标题前缀匹配（如 `"宝具"` 匹配 `宝具(强化后)`）
- `pattern=` — 正则匹配（如 `/技能` 用 `^技能[123]`）
- `exact=` — 精确匹配（如 `/资料` 用 `资料(角色详情)`）

### 5.2 Playwright 截图引擎（`wiki_screenshot.py`，核心模块）

要点：

- **共享浏览器实例**：模块级单例 `_browser` + `asyncio.Lock`，所有截图复用同一个无头 Chromium（`--no-sandbox`、`--disable-dev-shm-usage`），每次截图新建 page、用完关闭
- **URL 策略**：先试直达 `https://fgo.wiki/w/{中文名}`，失败回退 `index.php?search=` 搜索页
- **页面清洗**：注入 CSS 隐藏侧边栏/导航/页脚/广告/编辑链接；滚动全页触发懒加载图片（`data-src` → `src`），等待可见图片 `complete`
- **章节切分**：JS 收集 `#mw-content-text` 下所有 h2/h3 标题的 Y 坐标；「技能」大节特殊处理，h3 子标题单独成节
- **tabber 处理**：收集 `.tabber` 面板（如宝具「强化前/强化后」），逐面板切换 `location.hash` 后分别截图，标题追加 `(标签)`
- **两种截图方式**：
  - 表格章节（宝具/技能/职阶技能/追加技能/资料）→ 用 `locator("table.wikitable.nomobile").nth(idx)` 精确截表
  - 非表格章节（素材需求/牵绊/各阶段图标等）→ 按标题边界 clip 截图，超长章节（>1400px）自动分片并加 `(续)` 后缀
- **追加技能**多表自动垂直拼接（Pillow）
- **跳过无效章节**：相关礼装 / 语音 / 成长曲线 / 国服未来PickUp / 注释和链接 / 愚人节
- **兜底**：章节解析失败时返回整页全高截图（标题「从者页面」）

### 5.3 别名系统（三套 YAML）

统一模式：`{显示名: {atlas_id?, category?, name_jp?, name_en?, aliases: [...]}}`，查找时先精确匹配、再包含匹配（如 `妖精骑士` 命中 `妖精骑士女王`）。

| 文件 | 行数 | 用途 |
|---|---|---|
| `data/aliases/servant_cn.yaml` | ~3900 | 从者（含日文名、英文名、昵称） |
| `data/aliases/equip_cn.yaml` | ~17400 | 礼装 |
| `data/aliases/material_cn.yaml` | ~790 | 素材/道具（含 category、日文名、英文名） |

未命中时的提示会引导用户到对应 YAML 文件添加映射。

### 5.4 Atlas Academy 数据源（`atlas_client.py`）

- `aiohttp` session 复用（模块级单例）
- 内存缓存 `_servant_cache[(region, id)]`
- `get_servant_detail_cn_with_jp_growth_fallback()`：CN 为主（中文名/文本/资源），若 CN 的 `atkGrowth`/`hpGrowth` 不足 120 级则用 JP 补齐，缺失基础字段（`atkBase`/`atkMax`/`hpBase`/`hpMax`/`lvMax`）也从 JP 兜底

---

## 6. 运行与开发

### 6.1 环境配置

`.env`（已 gitignore）中的关键项：

- `DRIVER` / `HOST` / `PORT` / `LOG_LEVEL` — NoneBot 运行参数
- `ONEBOT_WS_URLS` / `ONEBOT_ACCESS_TOKEN` — OneBot v11 反向 WebSocket 连接
- `COMMAND_START` — 命令前缀

### 6.2 启动

```powershell
.\run_bot.ps1
# 等价于
.\.venv\Scripts\python.exe bot.py
```

### 6.3 调试

- `debug_all_commands.py` — 从别名表随机选从者 + 礼装，依次执行全部查询命令逻辑，把每张截图落到 `screenshots/`（gitignore），用于全命令回归
- 单命令测试：`test_card.py` / `test_card_debug.py`
- 注意 Windows 终端 GBK 编码问题，调试脚本里已做 `sys.stdout.reconfigure(encoding="utf-8")` 处理

### 6.4 离线导入兼容

`plugins/fgo/__init__.py` 检测 NoneBot 环境：未初始化时跳过命令加载，保证测试脚本可以 `import plugins.fgo.services.*` 而不触发 NoneBot 依赖。

---

## 7. 已知问题与待办

**已解决（2026-10-03）**：

- ~~`/help` 过时~~ → 已重写，列出全部 16+ 命令
- ~~旧代码未清理~~ → 已删除 `render/`（旧 PIL 渲染器）、`services/assets.py`、`test_render.py`、`test_screenshot.py`、`tools/test_render_svt.py`、`tools/svt2.json`
- ~~`_find_table_indices` 参数漏传~~ → 已修复，`nxt` 正常传入
- ~~资料个人资料1~6 截图空白~~ → 根因：Playwright 的 `clip` 是**视口相对坐标**，`location.hash` 切换面板后页面滚动，按文档坐标截图落到空白区；修复为直接 `locator.screenshot()` 截 panel 元素
- ~~卡面「从者名+数字」命名未匹配~~ → 如 `玄奘三藏1.png` 这类文件命名不在原模式表中；已把从者名传入 JS 并在 STAGE_PATTERNS 末尾加入 `从者名+N` 兜底模式

**仍待处理**：

1. **RapidFuzz 未使用**：依赖已声明，后续可用于别名模糊匹配
2. **工作区未收口**：`git status` 有大量修改未提交（`commands/query/*` 全部 M），根目录仍有多个未跟踪的调试脚本（`debug_all_commands.py`、`gen_material_aliases.py`、`scrape_materials*.py`、`test_card*.py` 等），建议归入 `tools/` 或清理
3. **`/查询` 只发第一张截图**（`fr.sections[0]`），完整信息需配合其他分项命令查看
4. **无自动化测试体系**：截图类功能依赖 fgo.wiki 页面结构，页面改版会导致截图失效；`debug_all_commands.py` 已覆盖全部命令（含素材），作为人工回归工具
5. **clip 截图依赖 `scrollY=0` 前提**：普通章节的 clip 截图使用文档坐标，依赖截图前页面滚动位置在顶部（当前流程保证，但较脆弱），后续可统一改为元素定位截图

---

## 8. 历史架构演变

| 阶段 | 时间 | 方案 |
|---|---|---|
| 1 | 早期 | PIL 手动绘制 Mooncell 风格信息图（`render/svt_mooncell.py`） |
| 2 | ~7 月 | **取消生图，改用 Playwright 截取 fgo.wiki 页面**（提交 `170523b`），区服偏好功能移除 |
| 3 | ~7 月下旬 | 截图引擎完善：章节切分、tabber 多版本、表格精确截图、超长分片 |
| 4 | 近期 | 扩展礼装查询（别名表 + `wiki_equip_screenshot.py`，提交 `6b4caf8`）、素材查询（`wiki_material_screenshot.py`）、卡面原图提取（`wiki_card.py`） |

## 9. 未来开发方向

- 更新 `/help` 命令清单
- 清理废弃代码（`render/`、`assets.py`）与根目录调试产物
- 提交当前工作区的未提交改动
- `commands/query/__init__.py` 中已预留注释：`/enemy`（敌人查询）、`/quest`（关卡查询）
- 建立截图回归测试体系，降低 fgo.wiki 页面改版带来的隐性故障风险
- 别名模糊匹配（RapidFuzz）优化查询体验

---

## 10. 一句话总结

项目已从「PIL 生图原型」进化为「**别名表 + Atlas 数据 + fgowiki 网页截图**」的稳定查询体系：从者 11 个命令、礼装/素材各 1~2 个命令全部可用；当前重点是收口工作区、更新 `/help`、清理废弃代码，然后继续扩展敌人/关卡等新查询能力。
