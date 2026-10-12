"""RSS 资讯抓取器（模板 + 可用）。

演示“如何新增一个数据源”：实现 BaseFetcher.run，把条目写入 raw_items(kind=news)。
学校官网/研招网公告等无 RSS 时，可仿照本类写一个 school_site 抓取器。
"""
import xml.etree.ElementTree as ET
from datetime import datetime

import requests

from ..storage import repo
from .base import BaseFetcher


class RssFetcher(BaseFetcher):
    name = "RSS资讯"
    type = "rss"

    def __init__(self, feed_url, name=None, timeout=20, **options):
        super().__init__(**options)
        self.feed_url = feed_url
        if name:
            self.name = name
        self.timeout = timeout

    def run(self, session):
        src = repo.get_or_create_source(session, self.name, self.type, url=self.feed_url)
        resp = requests.get(self.feed_url, timeout=self.timeout,
                            headers={"User-Agent": "dlmu-fetcher/0.1"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        new = 0
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "").strip()
            if not title:
                continue
            _, created = repo.add_raw_item(
                session, title=title, kind="news", content=desc[:2000],
                url=link or None, source_id=src.id)
            if created:
                new += 1
        return {"source": self.name, "new_items": new}
