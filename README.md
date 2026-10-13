# dlmu — 考研信息分享自媒体自动化

周期性**自主选题** → 抓取考研数据 → 生成**图文**（未来视频）→ **人工确认** → 多平台发布 → 数据回流。
选题分**公共**与**学校定向**两类。

**组件解耦，数据库即契约**：抓取(Fetchers) / 创作(Creator) / 发布(Publisher) / 回流(Analytics)
各自独立，只通过一个共享数据库交换数据。架构与表结构见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 快速开始

```bash
# 1) 安装依赖（建议虚拟环境）
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2) 配置（复制后按需修改；LLM 三项留空则创作走模板占位，链路仍可跑通）
cp .env.example .env

# 3) 建表
python -m pipeline.cli init-db

# 4) 抓取：导入研招网硕士目录样本（--pool 指定目标学校池）
python -m pipeline.cli fetch --source yz --path data/yz_majors.sample.csv --pool 清华大学 北京大学 浙江大学

# 5) 创作：选题 → 文案 → 图文卡片 → 草稿
python -m pipeline.cli create --limit 3

# 6) 查看草稿（待人工确认）
python -m pipeline.cli list-drafts
```

接入大模型：在 `.env` 填 `LLM_BASE_URL / LLM_API_KEY / LLM_MODEL`（OpenAI 兼容，指向你已有模型网关），
创作即自动生成正式文案；否则输出模板占位内容。

## 两种文案生成方式

- **外部 LLM（`create`）**：调 `.env` 里配置的 OpenAI 兼容接口生成文案（需要 LLM key）。
- **WorkBuddy Agent（`select` + `save-draft`，推荐，无需任何 LLM key）**：
  1. `python -m pipeline.cli select --limit 3 --out outputs/agent_brief.json` 导出候选选题简报（含学校/专业/科目）；
  2. 由 WorkBuddy（内置大模型）读简报、亲自写**5-8 页翻页图**文案，存成 `outputs/agent_drafts.json`。每篇含 `title/subtitle/tags/body/closing` 和 `pages:[{heading, points[]}]`（3-6 个内容页，与封面+尾页合计 5-8 页，按「引入→干货→避坑」的逻辑排序）；
  3. `python -m pipeline.cli save-draft --file outputs/agent_drafts.json` 落草稿（`generator=workbuddy`）并渲染图文卡片。

已配置**定时任务「dlmu 考研文案自动生成」**（每 2 天 09:00 自动跑：采集→选题→Agent 写文案→草稿+卡片），可在自动化管理里调整频率或暂停。

## 目录

```
pipeline/
  config.py          # 环境变量配置
  storage/           # 数据契约：models / db / repo（组件间唯一耦合点）
  fetchers/          # 抓取器：yz_importer(研招网CSV) / rss_fetcher(模板)
  creator/           # 创作 Agent：selector 选题 / copywriter 文案 / card_renderer 卡片 / runner
  cli.py             # 命令行入口
data/                # 研招网样本数据（可替换为完整数据集）
outputs/             # 生成的草稿与卡片（gitignore）
```

## 路线图

- **Phase 1（当前）**：采集 → 入库 → 创作草稿 跑通。
- Phase 2：发布 Agent（先手动导出，再接 social-auto-upload 等自动发布到小红书/抖音）。
- Phase 3：视频生成。
- Phase 4：数据回流优化选题。
