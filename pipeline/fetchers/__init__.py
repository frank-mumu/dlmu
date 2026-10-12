"""抓取器注册表：新增数据源只需在此登记。"""
from .rss_fetcher import RssFetcher
from .yz_importer import YzCatalogImporter

REGISTRY = {
    "yz": YzCatalogImporter,
    "rss": RssFetcher,
}


def get_fetcher(kind, **options):
    if kind not in REGISTRY:
        raise ValueError(f"未知抓取器: {kind}，可选: {list(REGISTRY)}")
    return REGISTRY[kind](**options)


__all__ = ["REGISTRY", "get_fetcher", "YzCatalogImporter", "RssFetcher"]
