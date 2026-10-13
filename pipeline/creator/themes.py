"""内容主题（一次性定义）。

以「考研咨询专业老师」视角设计，覆盖学生与家长最关心的维度：
- 学校定向（scope=school）：针对目标学校池（如大连海事大学）逐校生成
- 公共（scope=general）：与具体学校无关、但与考研强相关

每个主题带 search_templates（{school} 占位符会被学校名替换），供全网抓取构造查询词。
修改本列表后重新运行 `python -m pipeline.cli seed-themes` 即可生效（已存在的主题按 key 更新）。
"""
from ..storage import repo

# audience: 学生 / 家长 / 通用
THEMES = [
    # ---------------- 学校定向（大连海事大学等目标学校） ----------------
    {
        "key": "major_intro",
        "name": "院校专业解读",
        "description": "大连海事大学王牌/特色学院与硕士专业全解析：学科评估、专业实力、适合谁考。",
        "audience": "学生",
        "scope": "school",
        "search_templates": [
            "{school} 考研 专业介绍 特色专业 学科评估",
            "{school} 研究生 王牌专业 优势学科 排名",
        ],
    },
    {
        "key": "admission_stats",
        "name": "报录数据透视",
        "description": "报录比、复试线、招生人数年度变化，用数据判断上岸难度与性价比。",
        "audience": "学生",
        "scope": "school",
        "search_templates": [
            "{school} 考研 报录比 复试分数线 近三年",
            "{school} 硕士研究生 招生人数 2026 拟录取",
        ],
    },
    {
        "key": "exam_books",
        "name": "考试科目与参考书",
        "description": "各专业考什么、官方参考书目与考试大纲变动，避免复习方向跑偏。",
        "audience": "学生",
        "scope": "school",
        "search_templates": [
            "{school} 考研 专业课 参考书目 考试大纲",
            "{school} 硕士 初试科目 官方大纲 变动",
        ],
    },
    {
        "key": "supervisor_research",
        "name": "导师与科研方向",
        "description": "重点导师、实验室与优势科研方向，帮学生选对赛道、写对邮件。",
        "audience": "学生",
        "scope": "school",
        "search_templates": [
            "{school} 研究生 导师 研究方向 重点实验室",
            "{school} 优势学科 科研平台 团队",
        ],
    },
    {
        "key": "employment",
        "name": "就业与薪酬前景",
        "description": "毕业去向、行业分布与薪资水平——学生看发展、家长看饭碗。",
        "audience": "通用",
        "scope": "school",
        "search_templates": [
            "{school} 研究生 就业质量报告 毕业去向 薪资",
            "{school} 硕士 就业率 主要就业行业",
        ],
    },
    {
        "key": "scholarship",
        "name": "奖助学金与学费",
        "description": "学费标准、各类奖学金与国家/学业助学金、助研津贴，家长最关心的成本账。",
        "audience": "家长",
        "scope": "school",
        "search_templates": [
            "{school} 研究生 学费 奖助学金 国家奖学金 标准",
            "{school} 硕士研究生 助研津贴 学业奖学金 覆盖比例",
        ],
    },
    {
        "key": "campus_life",
        "name": "校园生活与城市",
        "description": "宿舍、食堂、校区与所在城市气候/生活成本，家长判断「孩子去那儿舒不舒服」。",
        "audience": "家长",
        "scope": "school",
        "search_templates": [
            "{school} 研究生 宿舍 食堂 校区 生活条件",
            "{school} 所在城市 气候 生活成本 研究生日常",
        ],
    },
    {
        "key": "retry_adjust",
        "name": "复试与调剂策略",
        "description": "复试内容、差额比与院内/校际调剂机会，临门一脚与兜底方案。",
        "audience": "学生",
        "scope": "school",
        "search_templates": [
            "{school} 考研 复试 内容 差额复试比 经验",
            "{school} 调剂 院内 校际 机会 名额",
        ],
    },
    # ---------------- 公共（与具体学校无关，但与考研强相关） ----------------
    {
        "key": "policy",
        "name": "考研政策与动态",
        "description": "研招网政策、扩招/缩招、推免比例与统考改革，第一时间跟住大势。",
        "audience": "通用",
        "scope": "general",
        "search_templates": [
            "2026 考研 研招网 政策 变化 扩招 统考",
            "考研 推免比例 改革 最新通知 教育部",
        ],
    },
    {
        "key": "prep_plan",
        "name": "备考规划与经验",
        "description": "复习时间表、公共课/专业课方法、冲刺与心态，干货最易被收藏转发。",
        "audience": "学生",
        "scope": "general",
        "search_templates": [
            "考研 复习规划 时间表 公共课 专业课 经验",
            "考研 冲刺 备考 方法 心态 高分经验",
        ],
    },
    {
        "key": "pitfall",
        "name": "报考避坑指南",
        "description": "常见误区、信息差与择校陷阱，帮考生少走弯路、避雷。",
        "audience": "通用",
        "scope": "general",
        "search_templates": [
            "考研 报考 避坑 常见误区 信息差",
            "考研 择校 陷阱 最容易踩的坑 真相",
        ],
    },
    {
        "key": "cross_exam",
        "name": "跨考与特殊群体",
        "description": "跨专业、同等学力、退役士兵计划等政策的门槛与机会。",
        "audience": "学生",
        "scope": "general",
        "search_templates": [
            "考研 跨专业 跨考 难度 成功率 建议",
            "同等学力 考研 退役士兵 计划 政策 条件",
        ],
    },
]


def seed_themes(session):
    """把 THEMES 写入数据库（按 key 去重/更新）。"""
    repo.seed_themes(session, THEMES)


def active_themes(session):
    return repo.active_themes(session)


def build_search_queries(theme, school_name=None):
    """根据主题构造全网抓取查询词列表。"""
    out = []
    for tpl in (theme.search_templates or []):
        out.append(tpl.format(school=school_name or ""))
    return out
