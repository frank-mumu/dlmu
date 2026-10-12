"""dlmu — 考研信息分享自媒体自动化流水线。

组件解耦：抓取(Fetchers) / 创作(Creator) / 发布(Publisher) / 回流(Analytics)，
通过共享数据库(见 ARCHITECTURE.md)交换数据。
"""

__version__ = "0.1.0"
