# fgo-qq-bot 项目梳理与开发说明

## 1. 项目概述

`fgo-qq-bot` 是一个基于 **NoneBot2 + OneBot v11** 的 FGO 信息查询 Bot，目标是在 QQ 上提供从者等 FGO 相关信息的查询功能。

当前仓库地址：

- `fakelego/fgo-qq-bot`

仓库描述：

- 一个可以在 qq 上使用的 fgo 信息查询 bot

当前项目状态：

- 已完成基础机器人启动链路
- 已完成 FGO 插件基础结构划分
- 已完成区服偏好存储
- 已完成从者查询主链路的雏形
- 已开始进行 Mooncell 风格图片渲染
- 仍处于“原型到可用版本”的过渡阶段，尚未完整收口

---

## 2. 当前仓库结构概览

根据当前仓库代码，核心结构如下：

```text
fgo-qq-bot/
├─ bot.py
├─ README.md
├─ requirements.txt
├─ run_bot.ps1
├─ gen_aliases.ps1
├─ fgo.db
├─ svt2.json
├─ svt_table.png
├─ mini.png
├─ plugins/
│  └─ fgo/
│     ├─ __init__.py
│     ├─ state.py
│     ├─ storage_sqlite.py
│     ├─ commands/
│     │  ├─ __init__.py
│     │  ├─ meta/
│     │  │  ├─ __init__.py
│     │  │  ├─ help.py
│     │  │  ├─ ping.py
│     │  │  ├─ region.py
│     │  │  ├─ setregion.py
│     │  │  └─ setgroupregion.py
│     │  └─ query/
│     │     ├─ __init__.py
│     │     └─ svt.py
│     ├─ services/
│     │  ├─ assets.py
│     │  └─ query/
│     │     └─ svt_search.py
│     ├─ stores/
│     │  ├─ aliases_servant_cn.py
│     │  └─ atlas_client.py
│     ├─ render/
│     │  ├─ svt_card.py
│     │  └─ svt_mooncell.py
│     └─ data/
│        ├─ aliases/
│        ├─ cache/
│        └─ guides.sample.yaml
└─ tools/
   ├─ atlas_collection_map.json
   └─ gen_servant_cn_aliases_from_mooncell.py
```

---

## 3. 项目使用的技术栈

从当前代码和依赖可以看出，项目主要使用了以下技术：

### 核心框架
- Python
- NoneBot2
- OneBot v11 Adapter

### 服务与协议
- FastAPI
- Uvicorn

### 数据与网络
- aiohttp
- SQLite
- PyYAML

### 图像处理
- Pillow（代码中已使用，建议显式写入依赖）

### 其他
- RapidFuzz（依赖中存在，后续可用于模糊匹配优化）

---

## 4. 当前项目已经实现的部分

### 4.1 机器人启动入口

入口文件是 `bot.py`：

```python
import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

nonebot.init()
driver = nonebot.get_driver()
driver.register_adapter(OneBotV11Adapter)

nonebot.load_plugins("plugins")

if __name__ == "__main__":
    nonebot.run()
```

说明当前机器人启动逻辑是：

1. 初始化 NoneBot
2. 注册 OneBot v11 适配器
3. 自动加载 `plugins` 目录
4. 启动 Bot

---

### 4.2 插件加载逻辑

`plugins/fgo/__init__.py` 中做了兼容处理：

- 若在 NoneBot 环境中运行，则加载命令模块
- 若离线导入（测试/脚本），则不强制加载命令

这说明项目已经兼顾了：

- 正常 Bot 运行
- 独立脚本测试 / 离线渲染

---

### 4.3 已实现的命令

#### Meta 类命令
- `/ping`
- `/help`
- `/region`
- `/setregion`
- `/setgroupregion`

#### Query 类命令
- `/svt`

其中 `/help` 中也已经规划了未来待实现的命令：

- `/ce`
- `/mat`
- `/guide`

---

### 4.4 区服逻辑

项目已经实现了用户/群的区服偏好设置，存储在 SQLite 中。

数据库文件：

- `fgo.db`

核心逻辑位于：

- `plugins/fgo/storage_sqlite.py`

已实现能力：

- 设置用户默认区服
- 设置群默认区服
- 根据上下文解析当前生效区服

规则：

- 群聊：`群默认 > 用户默认 > cn`
- 私聊：`用户默认 > cn`

这是当前项目中的一个完整子系统。

---

### 4.5 从者查询主链路

当前 `/svt` 的整体设计思路是：

1. 用户输入关键词
2. 判断是否显式指定区服
3. 若未显式指定，则走上下文区服解析
4. 使用中文别名映射查到 `atlas_id`
5. 调用 Atlas Academy API 获取从者 detail
6. 用渲染器将 detail 生成为图片
7. 发送图片消息到 QQ

这一链路已经具备雏形。

---

### 4.6 中文别名系统

中文别名系统位于：

- `plugins/fgo/stores/aliases_servant_cn.py`

对应数据文件：

- `plugins/fgo/data/aliases/servant_cn.yaml`

功能：

- 支持中文名
- 支持别名列表
- 支持命中后的展示名
- 支持简单包含匹配

这一步的意义很大，因为 FGO 中文环境下的查询体验高度依赖别名系统。

---

### 4.7 Atlas Academy 数据源接入

远程数据源主要通过：

- `plugins/fgo/stores/atlas_client.py`

当前已实现：

- `aiohttp` Session 复用
- Atlas API 基础 GET
- 基础缓存
- 按 id 获取从者基础信息
- 按区服获取从者 detail

此外，从代码调用关系可看出，你已经在尝试做：

- CN 数据优先
- JP 成长曲线回退

这是一个合理的数据整合方向。

---

### 4.8 图片渲染系统

当前已经有两个渲染文件：

- `plugins/fgo/render/svt_card.py`
- `plugins/fgo/render/svt_mooncell.py`

其中最近主要在开发的是：

- `svt_mooncell.py`

当前渲染方向：

- 大画布排版
- 左侧基础数值表
- 右侧立绘展示
- Q/A/B 指令卡展示
- 底部来源 footer
- 尽量贴近 Mooncell 页面风格

这说明项目正在从“可查询”向“可展示、可观感化”推进。

---

### 4.9 静态资源缓存

图片资源缓存逻辑位于：

- `plugins/fgo/services/assets.py`

缓存策略：

- 使用 URL 的 SHA1 作为文件名
- 缓存到本地目录
- 若本地存在缓存则直接读取
- 否则重新下载并写入缓存

缓存目录：

- `plugins/fgo/data/cache/assets`

该设计可减少重复网络请求。

---

### 4.10 辅助脚本

当前项目包含辅助脚本：

#### 启动脚本
- `run_bot.ps1`

内容：
```powershell
.\.venv\Scripts\python.exe bot.py
```

#### 别名生成脚本
- `gen_aliases.ps1`

内容：
```powershell
.\.venv\Scripts\python.exe tools\gen_servant_cn_aliases_from_mooncell.py
echo $LASTEXITCODE
```

这说明项目当前的开发环境明显偏向：

- Windows
- PowerShell
- 本地虚拟环境

---

## 5. 推测的项目原始搭建步骤

根据当前仓库内容，可以较高可信度地反推出项目最初的搭建流程。

### 第一步：创建项目目录
新建一个 Python 项目目录，例如：

```bash
mkdir fgo-qq-bot
cd fgo-qq-bot
```

### 第二步：创建虚拟环境

```bash
python -m venv .venv
```

Windows PowerShell 激活：

```powershell
.\.venv\Scripts\Activate.ps1
```

### 第三步：安装依赖

```bash
pip install -r requirements.txt
```

### 第四步：创建最小 NoneBot 启动入口
编写 `bot.py`：

- `nonebot.init()`
- 注册 OneBot v11 Adapter
- 加载插件目录
- 启动机器人

### 第五步：建立插件结构
建立：

- `plugins/fgo/commands`
- `plugins/fgo/services`
- `plugins/fgo/stores`
- `plugins/fgo/render`
- `plugins/fgo/data`

### 第六步：优先做基础命令与状态层
先实现：

- `/ping`
- `/help`
- `/region`
- `/setregion`
- `/setgroupregion`

并建立 SQLite 持久化存储。

### 第七步：接入 Atlas 数据源
在 `stores` 层实现：

- API 请求
- Session 复用
- servant detail 获取
- 基础缓存

### 第八步：建立中文别名体系
建立：

- YAML 别名文件
- 本地别名查询逻辑
- Mooncell 辅助别名生成脚本

### 第九步：实现 `/svt` 查询链路
打通：

- 关键词 → 别名 → atlas_id → detail → 渲染 → 发送消息

### 第十步：开发图片渲染器
使用 Pillow 开始做 Mooncell 风格页面图。

---

## 6. 当前项目总体逻辑

项目现在的运行逻辑可以概括为：

### 6.1 启动阶段
- 运行 `bot.py`
- 初始化 NoneBot
- 注册 OneBot v11
- 加载 `plugins`

### 6.2 插件初始化阶段
- `plugins/fgo/__init__.py` 判断当前环境
- 若是 Bot 环境则加载命令

### 6.3 命令接收阶段
- 用户发送 `/ping`、`/region`、`/svt` 等命令
- `commands` 层负责接收消息与参数

### 6.4 状态解析阶段
- 若命令依赖区服，则走 `storage_sqlite.resolve_region()`

### 6.5 数据查询阶段
- 先在本地别名系统中解析关键词
- 命中后拿到 `atlas_id`
- 再向 Atlas Academy 请求结构化数据

### 6.6 渲染阶段
- 从者 detail 进入 `render` 层
- 生成 Mooncell 风格图片

### 6.7 回复阶段
- 将文本或图片通过 OneBot v11 发送回 QQ

---

## 7. 当前最需要解决的问题

结合代码现状和最近开发方向，当前最重要的问题主要有以下几个。

---

### 问题 1：`/svt` 主命令逻辑存在半重构状态

`plugins/fgo/commands/query/svt.py` 当前存在明显风险：

- 图片渲染逻辑与旧文本逻辑混杂
- 分支结构可疑
- `result.atlas` 的使用与 `SvtDetailResult` 定义不一致
- 很可能仍保留旧版返回逻辑的残余代码

这说明 `/svt` 还没有完全整理完。

---

### 问题 2：查询结果类型与命令使用方式不一致

`plugins/fgo/services/query/svt_search.py` 中的 `SvtDetailResult` 定义包含：

- `atlas_id`
- `cn_name`
- `mooncell_url`
- `detail`

但 `svt.py` 中仍有旧逻辑尝试访问：

- `result.atlas`

这说明调用方与返回结构未完全同步。

---

### 问题 3：`svt_mooncell.py` 中可能存在作用域和流程问题

当前渲染文件中可见以下风险：

- `extra` 的定义未在片段中看到
- `sess` 的定义未在片段中看到
- `buf` 在部分路径中可能未初始化
- footer/save/return 的逻辑嵌套在 `if cg_url:` 中，不够稳定

这类问题通常会造成：

- 渲染失败
- 局部路径正常、局部路径报错
- 代码后续难维护

---

### 问题 4：依赖声明可能不完整

代码中使用了：

- `PIL.Image`
- `PIL.ImageDraw`
- `PIL.ImageFont`

但 `requirements.txt` 当前内容中未明显看见 `Pillow`。

如果确实未声明，会导致新环境克隆后直接运行失败。

---

### 问题 5：README 几乎为空，项目难以复现

当前 `README.md` 只包含一句：

- 只是一个还没实现完整功能的项目

这不足以让其他人或未来的自己快速恢复开发环境，缺少：

- 安装步骤
- 启动方式
- OneBot 对接方式
- 命令说明
- 数据来源说明
- 图片渲染依赖说明

---

### 问题 6：仓库中混入运行产物和调试产物

根目录当前存在：

- `fgo.db`
- `mini.png`
- `svt2.json`
- `svt_table.png`

这些文件可能分别属于：

- 本地数据库
- 调试图片
- 离线测试输入
- 渲染输出样例

如果不加区分，会导致仓库结构逐渐混乱。

建议未来将其分类移动到：

- `docs/`
- `examples/`
- `tests/fixtures/`
- `tmp/`

或者纳入 `.gitignore`。

---

## 8. 最近开发重点总结

根据最近相关对话和当前代码，最近的开发重点主要集中在以下三方面：

### 8.1 Mooncell 风格渲染器重排
近期你一直在调整：

- 画布尺寸
- 左右布局比例
- 右侧立绘填充方式
- 指令卡样式
- footer 放置位置
- 留白和视觉平衡

说明最近的主目标是：

- 把从者详情图从“能生成”优化为“接近产品成品观感”

---

### 8.2 将本地项目推送到 GitHub
最近也处理了 GitHub 推送问题，包括：

- 初始化仓库
- 关联远程 origin
- 解决推送连接失败问题

现在仓库已经公开可见。

---

### 8.3 开始整理项目结构与后续规划
当前问题已从单点 bug 转向：

- 总体架构梳理
- 当前阶段问题识别
- 后续开发路线设计

这说明项目正从“试验性原型”转向“计划性开发”。

---

## 9. 如果现在重新搭建这个项目，推荐步骤

以下步骤适用于当前仓库的重新部署与本地恢复。

### 9.1 克隆仓库

```bash
git clone https://github.com/fakelego/fgo-qq-bot.git
cd fgo-qq-bot
```

### 9.2 创建虚拟环境

```bash
python -m venv .venv
```

PowerShell 激活：

```powershell
.\.venv\Scripts\Activate.ps1
```

### 9.3 安装依赖

```bash
pip install -r requirements.txt
```

如果尚未在依赖中写入 Pillow，请补装：

```bash
pip install Pillow
```

### 9.4 准备 OneBot v11 运行环境

当前仓库中尚未提供完整 `.env.example` 或 OneBot 对接说明，因此需要补充配置以下内容：

- OneBot 客户端（例如 go-cqhttp / Lagrange）
- 上报地址 / 反向 WebSocket / HTTP 配置
- NoneBot 监听配置

这部分建议后续补进 README。

### 9.5 准备字体文件

渲染器会尝试读取以下字体：

- `plugins/fgo/data/fonts/NotoSansCJKsc-Regular.otf`
- `plugins/fgo/data/fonts/SourceHanSansSC-Regular.otf`

如果字体缺失，中文渲染效果可能异常。

### 9.6 准备别名数据

确认存在：

- `plugins/fgo/data/aliases/servant_cn.yaml`

如果没有，可以考虑使用脚本生成：

```powershell
.\.venv\Scripts\python.exe tools\gen_servant_cn_aliases_from_mooncell.py
```

或运行：

```powershell
.\gen_aliases.ps1
```

### 9.7 启动 Bot

```powershell
.\run_bot.ps1
```

或者：

```powershell
.\.venv\Scripts\python.exe bot.py
```

### 9.8 基础功能测试

建议至少测试以下命令：

- `/ping`
- `/help`
- `/region`
- `/setregion cn`
- `/svt 摩根`

---

## 10. 未来继续开发该项目的推荐顺序

为了让项目从“能运行的原型”逐步变成“稳定、可扩展的 Bot”，推荐按以下顺序推进。

---

### 第一阶段：先修现有主链路稳定性

优先处理：

1. 修复 `plugins/fgo/commands/query/svt.py`
2. 修复 `plugins/fgo/render/svt_mooncell.py`
3. 补齐 `requirements.txt` 中的 Pillow
4. 确保 `/svt` 能稳定返回图片

目标：

- 让当前最核心功能稳定可用

---

### 第二阶段：补文档

补一份完整 README，至少包括：

- 项目简介
- 环境要求
- 安装与启动方法
- OneBot 接入说明
- 命令列表
- 开发中功能
- 数据来源
- 图片渲染说明

目标：

- 项目可复现
- 后续维护成本降低

---

### 第三阶段：清理仓库结构

建议处理：

- `fgo.db`
- `mini.png`
- `svt2.json`
- `svt_table.png`

将这些文件重新归类为：

- 示例
- 测试资源
- 文档截图
- 本地产物

目标：

- 仓库结构更清晰
- 减少未来维护混乱

---

### 第四阶段：继续完善渲染器

当前最接近成品化的部分就是渲染器，因此建议继续：

- 微调布局
- 增加职阶图标
- 增加更多信息字段
- 处理不同立绘比例
- 提升字体和边距统一性

目标：

- 从“功能图”升级为“成品图”

---

### 第五阶段：扩展功能命令

建议未来按如下顺序扩展：

1. `/svt`
2. `/ce`
3. `/mat`
4. `/guide`

原因：

- `/svt` 是当前主场景
- `/ce` 与从者查询结构最相近
- `/mat` 依赖名称与素材体系整理
- `/guide` 更偏链接整合

---

### 第六阶段：建立测试体系

建议增加：

- 离线渲染测试
- 示例输入 JSON
- 输出样图目录
- 功能回归测试脚本

目标：

- 调整渲染和数据逻辑时更安心
- 降低改坏现有功能的风险

---

### 第七阶段：配置化与可扩展化

未来建议逐步把以下内容配置化：

- 默认区服
- 字体路径
- 缓存路径
- Atlas API 超时时间
- 命令前缀
- 数据源开关

目标：

- 让项目更适合长期维护与扩展

---

## 11. 对当前项目的整体评价

### 优点
- 分层结构已经建立
- 核心启动链路清晰
- 区服状态设计合理
- Atlas 数据源选型正确
- 中文别名体系方向正确
- 图片渲染已经有明显成果
- 已经具备继续扩展为完整产品的基础

### 当前不足
- 文档严重不足
- 核心 `/svt` 命令存在半重构痕迹
- 渲染器存在流程和作用域风险
- 依赖可能未完整声明
- 仓库中包含运行与调试产物
- 配置和部署方式尚未系统化

---

## 12. 当前最推荐的下一步行动

建议优先按以下顺序执行：

1. 修复 `/svt` 命令逻辑
2. 修复 `svt_mooncell.py` 的结构性问题
3. 在 `requirements.txt` 中补齐 Pillow
4. 编写正式 README
5. 清理仓库根目录的调试/运行产物
6. 跑通完整 `/svt` 查询链路
7. 再继续优化 Mooncell 风格细节
8. 最后扩展 `/ce` 等新功能

---

## 13. 一句话总结

这个项目的方向、结构和核心链路都已经是对的；当前最重要的不是再盲目加功能，而是先把已有主链路和渲染链路收口、稳定、文档化，再进入下一阶段开发。