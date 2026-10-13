# dlmu 架构 — 考研信息分享自媒体自动化

目标：周期性**自主选题** → 抓取考研数据 → 生成**图文**（未来视频）→ **人工确认** → 多平台发布 → 数据回流优化。

**主题驱动的选题**：内容主题(Theme)**一次性定义**（见 `pipeline/creator/themes.py`，12 个：8 个学校定向 + 4 个公共）。
选题引擎**按「主题 × 日期」**产出 topic：每个学校定向主题对目标学校池每校生成一条，公共主题生成一条；
topic 带 `period`(YYYY-MM-DD)，同一主题同一天只产一条——保证周期任务每期都产新内容、不重复。

**抓取分两条路**：①结构化抓取（研招网目录 CSV、可选 RSS）；②**全网抓取**——由定时任务里的
Agent 用 WebSearch 围绕各主题采集公开信息，`ingest-web` 入库并按 `theme_key/scope` 打标，供创作按主题检索引用。

## 设计原则：组件解耦，数据库即契约

不采用单一"大产品"（如 AiToEarn / Easel 全家桶），而是拆成**独立组件**，彼此不直接调用，
只通过**一个共享数据库**交换数据。任一组件可独立替换、独立运行、独立排期。

```
                 ┌─────────────────────────────┐
                 │      共享数据库 (契约)        │
                 │  schools/majors/raw_items    │
                 │  topics/drafts/publish_jobs  │
                 │  metrics                     │
                 └─────────────────────────────┘
                   ▲          ▲            ▲          ▲
      ┌────────────┘          │            │          └────────────┐
      │ 写入                  │ 读取+写入   │ 读取待发布             │ 写入
┌──────────────┐      ┌──────────────┐  ┌──────────────┐      ┌──────────────┐
│  抓取器组件   │      │  创作 Agent   │  │  发布 Agent   │      │  数据回流组件 │
│  Fetchers    │ ──▶  │  Creator     │─▶│  Publisher   │ ──▶  │  Analytics   │
│ 研招网/官网/RSS│      │ 选题→文案→卡片│  │ 小红书/抖音  │      │ 播放/互动    │
└──────────────┘      └──────────────┘  └──────────────┘      └──────────────┘
   周期 cron            周期 cron          人工确认后触发          周期 cron
```

- **抓取器 Fetchers**：各自独立，把外部数据规范化后写入 `raw_items`（并按需回填 `schools`/`majors` 参考表）。
- **创作 Agent Creator**：周期性读取 `raw_items` + 学校池，经选题引擎产出 `topics`，再由大模型生成
  图文草稿（标题/正文/标签）+ 代码渲染图文卡片，写入 `drafts`（status=`pending_review`）。
- **人工确认闸**：审核 `drafts`，确认后置 `approved`（发布的前置条件）。
- **发布 Agent Publisher**：读取 `approved` 的草稿发布到各平台（**Phase 2，当前先手动导出发布**）。
- **数据回流 Analytics**：采集播放/互动写回 `metrics`，用于优化选题权重（Phase 4）。

## 数据契约（共享表结构）

| 表 | 归属组件 | 关键字段 | 说明 |
|----|---------|---------|------|
| `sources` | 抓取 | name,type,url,enabled,config | 数据源配置 |
| `themes` | 创作 | key(unique),name,description,audience,scope(search/general/both),search_templates,active | 内容主题（一次性定义） |
| `schools` | 抓取 | name(unique),code,province,level,in_pool | 学校；`in_pool=true` 即目标学校池 |
| `majors` | 抓取 | school_id,code,name,degree_type,direction,exam_subjects | 研招网专业目录 |
| `raw_items` | 抓取 | source_id,school_id,kind,title,content,url_hash(unique),theme_key,scope,published_at | 抓取的原始内容，按 url_hash 去重；`theme_key/scope` 供按主题检索 |
| `topics` | 创作 | theme_id,title,kind(public/school),school_id,period(YYYY-MM-DD),score,status,ref_item_ids | 选题候选；按(主题,日期,学校)去重 |
| `drafts` | 创作 | topic_id,platform,form,title,body,tags,assets,pages,status | 草稿；`status`: pending_review/approved/rejected/published |
| `publish_jobs` | 发布 | draft_id,platform,status,scheduled_at,result | 发布任务（Phase 2） |
| `metrics` | 回流 | platform,content_ref,views,likes,comments,collects | 表现数据（Phase 4） |

> 契约即这些表。新增组件只要遵守表结构即可接入，不影响其他组件。

## 组件接口约定

- 每个组件是 `pipeline/<component>/` 下的独立模块，有独立 CLI 入口，**只通过 SQLAlchemy 会话读写 DB**。
- 组件间不 import 彼此的业务代码（可共用 `pipeline.storage` 的 models/db）。
- 排期：两个周期任务（cron / WorkBuddy automation）——**抓取**（每日：结构化刷新 + Agent 全网采集入库）与**创作**（每 2 天：按主题产 topic + 写文案 + 渲染卡片）。

### CLI

```
init-db                    建表并 seed 主题
seed-themes / list-themes  写入 / 查看内容主题
fetch --source yz|rss|web  运行单个抓取器
fetch-all                  运行全部自主抓取器(RSS 种子 + 可选搜索 API)
ingest-web --file F        把 Agent 全网检索结果批量入库(打 theme_key/scope)
select --limit N --out F   导出候选选题简报(含主题/学校/素材)
save-draft --file F        按 Agent 文案落草稿 + 渲染 5-8 页卡片
create                     外部 LLM 模式创作(可选)
list-drafts / publish      查看草稿 / 发布(Phase 2 预留)
```

## 技术选型

- 语言：Python 3.11+（抓取/LLM/渲染生态最合适）。
- 存储：SQLAlchemy 2.x；开发用 SQLite，生产可无缝切 PostgreSQL（改 `DATABASE_URL`）。
- 大模型：OpenAI 兼容客户端，指向你已有的模型网关（`LLM_BASE_URL/LLM_API_KEY/LLM_MODEL`）。
- 图文卡片：Pillow 代码渲染（标题/要点/信息图），**零 AI 出图成本**；视频生成后续再接。
- 发布：Phase 2 复用成熟开源上传器（如 social-auto-upload）；当前手动导出。

## 分期

- **Phase 1（本次）**：存储契约 + 抓取框架 + 研招网数据导入 + 创作 Agent（选题/文案/卡片）跑通。
- Phase 2：发布 Agent（先手动导出，再接自动发布）。
- Phase 3：视频生成。
- Phase 4：数据回流优化选题。
