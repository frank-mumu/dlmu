# dlmu — 考研信息分享自媒体自动化

周期性**自主选题** → 抓取考研数据（含**全网抓取**）→ 生成**图文**（未来视频）→ **人工确认** → 多平台发布 → 数据回流。

**主题驱动的选题**：内容主题(Theme)一次性定义（12 个，8 个学校定向 + 4 个公共），
选题引擎**按「主题 × 日期」**产出 topic（贴合目标学校池，如大连海事大学），保证周期任务每期都产新内容。

**组件解耦，数据库即契约**：抓取(Fetchers) / 创作(Creator) / 发布(Publisher) / 回流(Analytics)
各自独立，只通过一个共享数据库交换数据。架构与表结构见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 快速开始

```bash
# 1) 安装依赖（建议虚拟环境）
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2) 配置（复制后按需修改；LLM 三项留空则创作走模板占位，链路仍可跑通）
cp .env.example .env

# 3) 建表（自动 seed 12 个内容主题）
python -m pipeline.cli init-db
python -m pipeline.cli list-themes        # 查看主题(key/scope/受众)

# 4) 抓取：导入研招网硕士目录样本 + 运行自主抓取器(RSS/可选搜索API)
python -m pipeline.cli fetch --source yz --path data/yz_majors.sample.csv
python -m pipeline.cli fetch-all

# 5) 选题：按「主题 × 日期」产出候选 topic，导出简报
python -m pipeline.cli select --limit 40 --out outputs/agent_brief.json

# 6) 创作：Agent 按简报写 5-8 页文案 → 落草稿 + 渲染卡片
python -m pipeline.cli save-draft --file outputs/agent_drafts.json

# 7) 查看草稿（待人工确认）
python -m pipeline.cli list-drafts
```

接入大模型：在 `.env` 填 `LLM_BASE_URL / LLM_API_KEY / LLM_MODEL`（OpenAI 兼容，指向你已有模型网关），
创作即自动生成正式文案；否则输出模板占位内容。

## 抓取：结构化 + 全网

- **结构化抓取**：`fetch --source yz`（研招网目录 CSV）；`fetch --source rss`（RSS 种子，见 `fetchers/sources.py`）。
- **全网抓取**：
  - 配置了 `SEARCH_API_URL` 时，`fetch-all` 会按「主题 × 学校/公共」自动搜索并入库；
  - 未配置时由**定时任务里的 Agent** 用 WebSearch 围绕各主题采集，`ingest-web` 入库（打 `theme_key/scope` 标签）。
- `fetch-all` 一次跑完全部自主抓取器；采集结果按 `theme_key/scope` 打标，创作时按主题检索引用。

## 两种文案生成方式

- **外部 LLM（`create`）**：调 `.env` 里配置的 OpenAI 兼容接口生成文案（需要 LLM key）。
- **WorkBuddy Agent（`select` + `save-draft`，推荐，无需任何 LLM key）**：
  1. `python -m pipeline.cli select --limit 40 --out outputs/agent_brief.json` 导出候选选题简报（含**主题**/学校/专业/科目/按主题检索的素材）；
  2. 由 WorkBuddy（内置大模型）读简报、用 WebSearch 补充该主题最新信息，亲自写**5-8 页翻页图**文案（每页内容丰富：小标题+引入句+编号要点+高亮提示），存成 `outputs/agent_drafts.json`。每篇含 `title/subtitle/highlights/tags/body/closing` 和 `pages:[{heading, lead, points[], callout?}]`（3-6 个内容页，与封面+尾页合计 5-8 页，按「引入→干货→避坑」排序）；
  3. `python -m pipeline.cli save-draft --file outputs/agent_drafts.json` 落草稿（`generator=workbuddy`）并渲染图文卡片。

## 定时任务（两个，可在自动化管理里调整/暂停）

- **dlmu 全网信息抓取(数据采集)**：每日 08:00 —— 结构化刷新 + Agent 全网采集入库（只采集，不创作）。
- **dlmu 考研文案自动生成**：每 2 天 09:00 —— 按主题选题 → Agent 写 5-8 页文案 → 草稿+卡片。

## 目录

```
pipeline/
  config.py          # 环境变量配置
  storage/           # 数据契约：models / db / repo（组件间唯一耦合点）
  fetchers/          # 抓取器：yz_importer(研招网CSV) / rss_fetcher / web_search(可选API) / sources(种子+查询)
  creator/           # 创作 Agent：themes 主题 / selector 选题 / copywriter 文案 / card_renderer 卡片 / runner
  cli.py             # 命令行入口
data/                # 研招网样本数据（可替换为完整数据集）
outputs/             # 生成的草稿与卡片（gitignore）
```

## 路线图

- **Phase 1（当前）**：采集 → 入库 → 创作草稿 跑通。
- Phase 2：发布 Agent（先手动导出，再接 social-auto-upload 等自动发布到小红书/抖音）。
- Phase 3：视频生成。
- Phase 4：数据回流优化选题。
