"""创作取材规范：把「围绕学校具体信息、不得编造」写成统一规范。

供两处复用：
1) topics_brief 把规范与可核实事实写进选题简报，让创作 Agent 直接看到；
2) 自动化任务提示词引用同一套口径，保证人工/自动产出一致。

核心原则：内容必须围绕大连海事大学的具体信息展开，凡是源数据没有的精确数字
（招生人数 / 复试线 / 报录比 / 学费 / 奖学金 / 排名）一律不得编造，用定性描述 +
「以学校官网 / 研招网最新公布为准」代替。复核(verifier)会据此反向校验。
"""
from ..storage import Major, repo
from . import style_guide


# 永远锚定的目标学校（项目定位：大连海事大学考研信息自媒体）
ANCHOR_SCHOOL_NAME = "大连海事大学"

# 源数据中没有、严禁编造的精确数字类型（供写作与复核共用）
FORBIDDEN_FABRICATED = [
    "招生人数 / 拟招生计划具体数字",
    "复试分数线 / 录取分数线",
    "报录比（如 5:1）",
    "学费金额 / 奖学金具体数额",
    "排名 / 具体名额数字",
    "推免比例百分比",
]

_VERIFIED_LABEL = "（数据来自研招网专业目录 / 学校官方，已核实）"
_UNVERIFIED_LABEL = "（源数据未提供具体数字，撰写为定性描述并注明以官网为准）"


def anchor_school(session):
    """返回项目锚定学校（大连海事大学）对象；没有则返回 None。"""
    return repo.school_by_name(session, ANCHOR_SCHOOL_NAME)


def writing_guide(theme_name, kind):
    """生成给创作 Agent 的取材指引文字。"""
    scope_note = (
        "本主题为学校定向，必须以上述 majors 的具体专业、代码、考试科目展开。"
        if kind == "school"
        else "本主题为公共/政策主题，请用大连海事大学的具体专业结构（如哪些专业考 408、"
             "专硕/学硕分布、航海类特色）来举例，把宏观政策落到本校考生身上。"
    )
    forbidden = "；".join(FORBIDDEN_FABRICATED)
    return (
        "【内容取材规范（必须遵循）】\n"
        f"1. 围绕大连海事大学的具体信息展开：每个内容页至少引用 1 处可核实的该校事实"
        f"（专业代码、考试科目代码、真实专业/学院名、官方公开信息），不要写放之四海皆准的空话。\n"
        f"2. {scope_note}\n"
        f"3. 严禁编造以下精确数字：{forbidden}。"
        f"源数据未提供的，用定性描述并注明「以学校官网/研招网最新公布为准」。\n"
        f"4. 数据口径：专业代码、考试科目代码以简报 majors 为准；其余事实以 ref_items 为准。"
        f"\n\n{style_guide.style_guide_text()}"
    )


def verified_facts_block(session, school):
    """把 DB 里已核实的具体事实列成可读条目（major code / 考试科目）。"""
    if not school:
        return []
    majors = session.query(Major).filter_by(school_id=school.id).all()
    facts = [f"{school.name}：{school.province or ''} {school.level or ''} {_VERIFIED_LABEL}"]
    for m in majors:
        facts.append(
            f"· {m.degree_type} {m.name}（代码 {m.code}）方向 {m.direction or '-'} "
            f"考试科目：{m.exam_subjects or '-'} {_VERIFIED_LABEL}"
        )
    return facts


def unverified_note():
    return (
        "以下信息源数据暂未提供具体数字，撰写时请勿编造，统一表述为"
        "「以学校研究生院官网 / 研招网最新招生简章与专业目录为准」："
        + "；".join(FORBIDDEN_FABRICATED)
    )
