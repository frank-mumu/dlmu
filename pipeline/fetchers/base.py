"""抓取器基类。

每个抓取器独立实现 run(session)：把外部数据规范化后写入契约表
（raw_items，并按需回填 schools/majors）。抓取器之间、与创作/发布组件互不依赖。
"""


class BaseFetcher:
    name = "base"
    type = "base"

    def __init__(self, **options):
        self.options = options

    def run(self, session):
        """执行抓取，写入 DB。返回一个可 JSON 化的统计 dict。"""
        raise NotImplementedError
