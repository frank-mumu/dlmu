"""全网搜索抓取器（可选）。

依赖外部搜索 API（在 .env 配置 SEARCH_API_URL / SEARCH_API_KEY）。
未配置时本抓取器直接跳过（graceful no-op），不影响其它抓取器；
届时由「定时任务里的 Agent」用内置 WebSearch 完成全网采集并调用 ingest-web 入库。

API 约定（尽量通用，可按你的网关调整）：
  GET {SEARCH_API_URL}?q=<query>
  Header: Authorization: Bearer <SEARCH_API_KEY>（若设置）
  期望返回 JSON，其中 results 为数组，元素含 title/link/snippet（字段名可容错）。
"""
import json

import requests

from ..config import settings
from ..storage import repo
from .base import BaseFetcher
from .sources import web_queries


class WebSearchFetcher(BaseFetcher):
    name = "全网搜索"
    type = "web_search"

    def __init__(self, school_names=None, per_theme=2, timeout=20, **options):
        super().__init__(**options)
        self.school_names = school_names
        self.per_theme = per_theme
        self.timeout = timeout

    def run(self, session):
        if not settings.search_api_url:
            return {"note": "SEARCH_API_URL 未配置，跳过（可用 Agent WebSearch + ingest-web 入库）",
                    "new_items": 0}
        queries = web_queries(session, school_names=self.school_names, per_theme=self.per_theme)
        headers = {}
        if settings.search_api_key:
            headers["Authorization"] = f"Bearer {settings.search_api_key}"
        new_items = 0
        for q, theme_key, scope in queries:
            try:
                resp = requests.get(settings.search_api_url, params={"q": q},
                                    headers=headers, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:  # 单条失败不阻断
                continue
            for item in self._extract(data):
                title = (item.get("title") or "").strip()
                if not title:
                    continue
                link = item.get("link") or item.get("url")
                snippet = item.get("snippet") or item.get("description") or ""
                _, created = repo.add_raw_item(
                    session, title=title, kind="web", content=snippet[:2000],
                    url=link or None, theme_key=theme_key, scope=scope,
                    source_id=None)
                if created:
                    new_items += 1
        return {"queries": len(queries), "new_items": new_items}

    @staticmethod
    def _extract(data):
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("results", "items", "data", "webPages"):
                v = data.get(key)
                if isinstance(v, list):
                    return v
        return []
