"""抓取器注册表：新增数据源只需在此登记。

fetch_all() 运行所有「自主抓取器」（RSS 种子 + 全网搜索），无需外部 LLM。
yz_importer(研招网 CSV) 因需指定 CSV 路径，单独通过 `fetch --source yz` 调用。
"""
from . import sources
from .rss_fetcher import RssFetcher
from .web_search import WebSearchFetcher
from .yz_importer import YzCatalogImporter

REGISTRY = {
    "yz": YzCatalogImporter,
    "rss": RssFetcher,
    "web": WebSearchFetcher,
}

__all__ = ["REGISTRY", "get_fetcher", "fetch_all",
           "YzCatalogImporter", "RssFetcher", "WebSearchFetcher", "sources"]


def get_fetcher(kind, **options):
    if kind not in REGISTRY:
        raise ValueError(f"未知抓取器: {kind}，可选: {list(REGISTRY)}")
    return REGISTRY[kind](**options)


def fetch_all(session, school_names=None):
    """运行所有自主抓取器，返回汇总统计。"""
    stats = {}
    # 1) RSS 种子
    for feed in sources.RSS_FEEDS:
        try:
            f = RssFetcher(feed_url=feed["url"], name=feed["name"])
            stats[f"rss:{feed['name']}"] = f.run(session)
        except Exception as e:
            stats[f"rss:{feed['name']}"] = {"error": str(e)[:200]}
    # 2) 全网搜索（若已配置搜索 API）
    stats["web"] = WebSearchFetcher(school_names=school_names).run(session)
    return stats
