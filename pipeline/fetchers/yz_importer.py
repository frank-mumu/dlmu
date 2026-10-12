"""研招网硕士目录导入器。

数据来源为“已采集好的研招网硕士目录”（CSV，字段见 data/yz_majors.sample.csv），
避免直接高频爬取研招网触发风控。完整数据集可替换 data/ 下的 CSV。

职责：CSV → schools/majors 参考表 + 每校生成一条 raw_items(kind=catalog)，
供下游创作 Agent 的选题引擎消费。
"""
import csv

from ..storage import repo
from .base import BaseFetcher


class YzCatalogImporter(BaseFetcher):
    name = "研招网-硕士目录"
    type = "yz_catalog"

    def __init__(self, path, pool=None, **options):
        super().__init__(**options)
        self.path = path
        self.pool = set(pool or [])

    def run(self, session):
        src = repo.get_or_create_source(session, self.name, self.type, url=self.path)
        rows = self._read()
        by_school = {}
        for r in rows:
            by_school.setdefault(r["school_name"], []).append(r)

        new_majors = new_items = 0
        for sname, majors in by_school.items():
            sample = majors[0]
            in_pool = bool(self.pool) and (sname in self.pool)
            school = repo.upsert_school(
                session, sname, code=sample.get("school_code"),
                province=sample.get("province"), level=sample.get("level"),
                in_pool=in_pool)
            for m in majors:
                added = repo.add_major(
                    session, school, m.get("major_code"), m.get("major_name"),
                    m.get("degree_type"), m.get("direction"), m.get("exam_subjects"))
                if added:
                    new_majors += 1
            _, created = repo.add_raw_item(
                session,
                title=f"{sname} 硕士招生目录已同步（{len(majors)} 个专业方向）",
                kind="catalog",
                content=self._summary(school, majors),
                url=f"yz://catalog/{school.code or school.name}",
                source_id=src.id, school_id=school.id,
                meta={"major_count": len(majors), "level": school.level,
                      "province": school.province, "in_pool": in_pool})
            if created:
                new_items += 1
        return {"schools": len(by_school), "new_majors": new_majors, "new_raw_items": new_items}

    def _read(self):
        with open(self.path, newline="", encoding="utf-8-sig") as f:
            return [r for r in csv.DictReader(f) if r.get("school_name")]

    def _summary(self, school, majors):
        names = "、".join(sorted({m["major_name"] for m in majors})[:8])
        region = f"{school.province or ''}".strip()
        level = f"{school.level or ''}".strip()
        tag = " ".join(x for x in [region, level] if x)
        return (f"{school.name}（{tag}）硕士招生目录，覆盖 {len(majors)} 个专业方向，"
                f"含：{names} 等。")
