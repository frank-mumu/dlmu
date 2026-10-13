"""数据源清单：RSS 种子 + 全网搜索词生成。

- RSS_FEEDS：可在此增删学校官网/资讯站 RSS（无 RSS 的站点可后续写 school_site 抓取器）。
  抓取器对单个 feed 失败是容错的（跳过并继续）。
- web_queries(settings, session)：根据「活跃主题 × 目标学校池 / 公共」生成全网搜索词，
  供 web_search 抓取器或 Agent 使用。
"""
from ..creator import themes as theme_mod
from ..storage import repo


# 学校官网 / 研招资讯 RSS（按需增删；单条失败会被容错跳过）。
# 说明：多数高校站点无公开 RSS，故默认留空；「全网抓取」主要由 fetch 定时任务里的
# Agent 用 WebSearch 完成并 ingest-web 入库。若要启用 RSS，把下面的示例填上真实 feed 地址即可。
# 示例：
# RSS_FEEDS = [
#     {"name": "大连海事大学研究生院", "url": "<真实RSS地址>", "scope": "大连海事大学"},
#     {"name": "中国研究生招生信息网", "url": "<真实RSS地址>", "scope": "general"},
# ]
RSS_FEEDS = []


def web_queries(session, school_names=None, per_theme=2):
    """生成全网抓取查询词列表：[(query, theme_key, scope), ...]。

    school_names: 目标学校名列表（默认取学校池）。per_theme: 每个主题取前 N 个模板。
    """
    schools = ([s for s in repo.pool_schools(session)
                if s.name in (school_names or [])] if school_names
               else repo.pool_schools(session))
    queries = []
    for theme in theme_mod.active_themes(session):
        templates = (theme.search_templates or [])[:per_theme]
        if theme.scope in ("school", "both"):
            for school in schools:
                for tpl in templates:
                    queries.append((tpl.format(school=school.name), theme.key, school.name))
        if theme.scope in ("general", "both"):
            for tpl in templates:
                queries.append((tpl.format(school=""), theme.key, "general"))
    return queries
