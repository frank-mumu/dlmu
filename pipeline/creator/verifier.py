"""自动化复核：创作完成后，根据原始数据源校验生成内容是否准确有依据，避免胡编乱造。

两条数据源（原始事实的唯一权威）：
  1) 数据库专业目录（majors）：专业代码、考试科目代码、学位类型、方向 —— 结构化、已核实；
  2) 全网抓取原始素材（raw_items）：按主题/学校检索到的公开信息 —— 语义化、供交叉印证。

复核项（规则引擎，离线可跑；可选 LLM 增强）：
  A. 专业代码归属：草稿里出现的专业代码必须存在于专业目录，且同一页内出现的考试科目代码
     必须属于该专业，否则标记「科目代码疑似错误」。
  B. 疑似编造：出现精确数字（比例/分数/人数/名额/报录比/金额/排名）但原始数据源中找不到，
     标记「需核实（源数据未提供该具体数字）」—— 这正是胡编乱造高发区。
  C. 学校信息锚定度：每页是否至少引用 1 处大连海事大学可核实事实，分数低说明内容空泛。
  D.（可选）LLM 通读：把草稿+数据源交给大模型，逐页给出「有依据/部分/无依据」与问题清单。

复核结果写入创作目录（outputs/cards/topicN/）：review.json（机读）+ review.md（人读）。
"""
import datetime
import json
import os
import re

from ..config import settings
from ..storage import Major, RawItem, repo

# 6 位 / 4 位专业代码（如 030100、0823）
_MAJOR_CODE = re.compile(r"(?<!\d)(0\d{3}|\d{6})(?!\d)")
# 考试科目代码：10x/20x/30x/40x/62x/8[0-2]x
_SUBJ_CODE = re.compile(r"(?<!\d)(?:10[0-9]|20[0-9]|30[0-9]|40[0-9]|62[0-9]|8[0-2][0-9])(?!\d)")
# 通用公共课代码（任何专业都可能出现，不计入科目归属错误）
_UNIVERSAL_SUBJ = {"101", "199", "201", "204", "301", "302", "303", "311", "313", "396", "397"}

# 精确数字 + 单位（疑似编造高发区）。顺序：先长后短，避免 "50%" 被 "50" 抢先。
_NUM_RULES = [
    ("报录比", re.compile(r"\d+(?:\.\d+)?\s*:\s*1")),
    ("比例", re.compile(r"\d+(?:\.\d+)?\s*%")),
    ("金额", re.compile(r"\d+(?:\.\d+)?\s*万?\s*元")),
    ("人数", re.compile(r"\d+(?:\.\d+)?\s*万?\s*人")),
    ("名额", re.compile(r"\d+\s*名")),
    ("分数", re.compile(r"\d{2,3}\s*分")),
    ("排名", re.compile(r"第\s*\d+\s*名")),
]
# 句子切分（用于给出数字出现上下文）
_SENT_SPLIT = re.compile(r"[。！？；\n]+")


def _sentences(text):
    return [s.strip() for s in _SENT_SPLIT.split(text or "") if s.strip()]


def build_fact_base(session, topic):
    """从原始数据源构建复核基准：锚定学校 + 专业目录 + 全网素材。"""
    from . import prompts
    school = topic.school
    anchor = school or prompts.anchor_school(session)
    majors = (session.query(Major).filter_by(school_id=anchor.id).all()
              if anchor else [])

    major_by_code = {}
    subject_set = set()       # 该校用到的所有考试科目代码（裸数字，如 408）
    for m in majors:
        major_by_code[m.code] = m
        for s in (m.exam_subjects or "").split(";"):
            mm = re.match(r"\s*(\d+)", s.strip())
            if mm:
                subject_set.add(mm.group(1))

    # 原始素材：主题标签下的公共素材 + 锚定学校的素材
    raw = []
    theme_key = topic.theme.key if topic.theme else None
    if theme_key:
        raw += repo.all_raw_items(session, theme_key=theme_key, scope="general", limit=20)
    if anchor:
        raw += repo.all_raw_items(session, scope=anchor.name, limit=20)
    seen, raw_dedup = set(), []
    for it in raw:
        if it.title in seen:
            continue
        seen.add(it.title)
        raw_dedup.append(it)

    # 可核实事实文本（用于数字依据检索）+ 学校锚定词
    sources_text = []
    if anchor:
        sources_text.append(f"{anchor.name} {anchor.province or ''} {anchor.level or ''}")
    for m in majors:
        sources_text.append(
            f"{m.code} {m.name} {m.degree_type} {m.direction or ''} {m.exam_subjects or ''}")
    for it in raw_dedup:
        sources_text.append(f"{it.title} {it.content or ''}")
    sources_blob = "\n".join(sources_text)

    school_tokens = set()
    if anchor:
        school_tokens.add(anchor.name)
        if "大连海事" in anchor.name:
            school_tokens.add("海大")
    for m in majors:
        school_tokens.add(m.name)
        school_tokens.add(m.code)

    return {
        "anchor": ({"name": anchor.name, "province": anchor.province, "level": anchor.level}
                   if anchor else None),
        "school": ({"name": school.name, "province": school.province, "level": school.level}
                   if school else None),
        "majors": [{"code": m.code, "name": m.name, "degree_type": m.degree_type,
                    "direction": m.direction, "exam_subjects": m.exam_subjects}
                   for m in majors],
        "major_by_code": major_by_code,
        "subject_set": subject_set,
        "raw_items": [{"title": it.title, "scope": it.scope, "theme_key": it.theme_key,
                       "content": (it.content or "")[:800]} for it in raw_dedup],
        "sources_blob": sources_blob,
        "school_tokens": school_tokens,
    }


def _page_text(pg):
    """递归收集页面里所有文本（兼容 list/checks/steps/compare/stat/grid/quote 各布局字段）。"""
    chunks = []

    def walk(o):
        if isinstance(o, str):
            if o.strip():
                chunks.append(o)
        elif isinstance(o, (list, tuple)):
            for x in o:
                walk(x)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)

    walk(pg)
    return " ".join(chunks)


def _flatten(content):
    """把草稿压成（页码, 文本）序列：封面=0，内容页=1..n，尾页=end。"""
    blocks = []
    title = content.get("title", "")
    subtitle = content.get("subtitle", "")
    blocks.append(("封面", f"{title} {subtitle}"))
    for i, pg in enumerate(content.get("pages", []) or [], start=1):
        blocks.append((f"P{i}", _page_text(pg)))
    if content.get("closing"):
        blocks.append(("尾页", content.get("closing")))
    return blocks


def _grounded(page_text, fb):
    """该页是否引用了至少 1 处学校可核实事实。"""
    for tok in fb["school_tokens"]:
        if tok and tok in page_text:
            return True
    # 命中专业目录里的考试科目代码也算锚定
    for s in fb["subject_set"]:
        if s and s in page_text:
            return True
    return False


def verify_draft(content, fact_base, use_llm=None):
    """对一篇草稿做复核，返回报告 dict。use_llm=None 时按 settings.llm_ready + 环境变量决定。"""
    blocks = _flatten(content)
    content_pages = [b for b in blocks if b[0].startswith("P")]
    total_pages = len(content_pages)

    issues = []          # 全部问题（含定位）
    per_page = []        # 每页结论
    grounded = 0

    for tag, text in blocks:
        if not tag.startswith("P"):
            continue
        # —— 学校锚定度 ——
        is_grounded = _grounded(text, fact_base)
        if is_grounded:
            grounded += 1
        page_issues = []

        # —— A. 专业代码 / 考试科目代码是否属于该校真实目录 ——
        major_codes = set(_MAJOR_CODE.findall(text))
        subj_codes = set(_SUBJ_CODE.findall(text))
        school_subj_union = fact_base["subject_set"]  # 该校所有真实考试科目代码
        for code in major_codes:
            if code not in fact_base["major_by_code"]:
                issues.append({"level": "high", "type": "未知专业代码", "page": tag,
                               "detail": f"出现专业代码 {code}，但专业目录中不存在（疑似笔误/编造）"})
                page_issues.append(f"未知专业代码 {code}")
        for sc in subj_codes:
            if sc in _UNIVERSAL_SUBJ:
                continue
            if sc not in school_subj_union:
                issues.append({
                    "level": "high", "type": "未知考试科目代码", "page": tag,
                    "detail": (f"出现考试科目代码 {sc}，但大连海事大学专业目录中没有任何专业使用此代码"
                               f"（疑似编造或笔误）。已知有效代码示例：{sorted(school_subj_union)[:12]}")})
                page_issues.append(f"未知考试科目代码 {sc}")

        # —— B. 疑似编造精确数字 ——
        for label, pat in _NUM_RULES:
            for mt in pat.finditer(text):
                token = mt.group(0).replace(" ", "")
                if token in fact_base["sources_blob"]:
                    continue  # 源数据里有这个具体数字，视为有依据
                # 找所在句子做上下文
                ctx = ""
                for sent in _sentences(text):
                    if mt.group(0) in sent:
                        ctx = sent
                        break
                issues.append({
                    "level": "high", "type": f"疑似编造/{label}", "page": tag,
                    "detail": (f"出现具体数字「{token}」，但原始数据源（专业目录/全网素材）中"
                               f"未提供该数字，疑似无依据编造。上下文：{ctx}")})
                page_issues.append(f"疑似编造{label}：{token}")

        per_page.append({"page": tag, "grounded": is_grounded,
                        "issues": page_issues,
                        "verdict": "有问题" if page_issues else "OK"})

    # —— C. 学校锚定度统计 ——
    grounding_ratio = (grounded / total_pages) if total_pages else 0.0
    if grounding_ratio < 0.5 and total_pages:
        issues.append({"level": "mid", "type": "内容偏空泛", "page": "整体",
                       "detail": (f"仅 {grounded}/{total_pages} 个内容页引用了大连海事大学可核实事实，"
                                  f"其余页面缺乏学校具体信息，建议补充专业代码/考试科目等具体事实。")})

    # —— 汇总 ——
    high = [i for i in issues if i["level"] == "high"]
    mid = [i for i in issues if i["level"] == "mid"]
    if high:
        verdict = "NEEDS_REVIEW"
        summary = f"发现 {len(high)} 处高优先级问题（含疑似编造/代码错误），必须人工复核后再发布。"
    elif mid:
        verdict = "NEEDS_REVIEW"
        summary = f"无硬性错误，但 {len(mid)} 处需关注（如内容偏空泛），建议润色后发布。"
    else:
        verdict = "PASS"
        summary = "未发现疑似编造或代码错误，且内容已锚定学校具体信息，可进入人工确认。"

    report = {
        "verified_at": datetime.datetime.utcnow().isoformat() + "Z",
        "verdict": verdict,
        "summary": summary,
        "grounding": {"grounded_pages": grounded, "total_pages": total_pages,
                      "ratio": round(grounding_ratio, 2)},
        "counts": {"high": len(high), "mid": len(mid), "total": len(issues)},
        "issues": issues,
        "per_page": per_page,
        "fact_base": {
            "anchor_school": fact_base["anchor"],
            "school_topic": fact_base["school"],
            "majors_count": len(fact_base["majors"]),
            "raw_items_count": len(fact_base["raw_items"]),
            "raw_items": fact_base["raw_items"],
        },
        "llm_review": None,
    }

    # —— D. 可选 LLM 通读增强 ——
    if use_llm is None:
        use_llm = bool(settings.llm_ready and os.getenv("VERIFY_LLM"))
    if use_llm and settings.llm_ready:
        report["llm_review"] = _llm_review(content, fact_base)
    return report


def _llm_review(content, fact_base):
    """可选：用 DeepSeek 通读草稿+数据源，逐页给依据判定。失败仅标记 skipped。"""
    try:
        import requests
        src = fact_base["sources_blob"][:4000]
        draft_txt = json.dumps(content, ensure_ascii=False)
        sys_p = ("你是严谨的考研内容审核员。只依据给定的「原始数据源」判断草稿事实是否有依据，"
                 "不得脑补。输出 JSON：{\"pages\":[{\"page\":,\"verdict\":\"有依据|部分|无依据\","
                 "\"note\":\"\"}],\"unsupported\":[\"疑似无依据的具体断言\"],\"overall\":\"\"}")
        user = f"【原始数据源】\n{src}\n\n【待审草稿】\n{draft_txt}\n\n请严格按 JSON 输出。"
        url = settings.llm_base_url.rstrip("/") + "/chat/completions"
        resp = requests.post(url,
            headers={"Authorization": f"Bearer {settings.llm_api_key}",
                     "Content-Type": "application/json"},
            json={"model": settings.llm_model,
                  "messages": [{"role": "system", "content": sys_p},
                               {"role": "user", "content": user}],
                  "temperature": 0.2, "max_tokens": 1500, "response_format": {"type": "json_object"}},
            timeout=60)
        resp.raise_for_status()
        data = resp.json()["choices"][0]["message"]["content"]
        return json.loads(data)
    except Exception as exc:  # 不影响主流程
        return {"skipped": True, "error": str(exc)}


def _render_md(report, topic, content):
    """把报告渲染为可读 Markdown。"""
    lines = []
    lines.append(f"# 创作复核报告 · {content.get('title', '')}")
    lines.append("")
    lines.append(f"- 选题：{topic.title}（topic_id={topic.id}）")
    lines.append(f"- 复核时间（UTC）：{report['verified_at']}")
    lines.append(f"- **结论：{report['verdict']}** —— {report['summary']}")
    g = report["grounding"]
    lines.append(f"- 学校信息锚定度：{g['grounded_pages']}/{g['total_pages']} 页"
                 f"（{int(g['ratio']*100)}%）")
    c = report["counts"]
    lines.append(f"- 问题统计：高优先级 {c['high']} · 中优先级 {c['mid']} · 合计 {c['total']}")
    lines.append("")

    lines.append("## 逐页结论")
    lines.append("")
    lines.append("| 页 | 锚定学校 | 结论 | 问题 |")
    lines.append("| --- | --- | --- | --- |")
    for p in report["per_page"]:
        lines.append(f"| {p['page']} | {'✅' if p['grounded'] else '❌'} | {p['verdict']} | "
                     f"{'；'.join(p['issues']) or '—'} |")
    lines.append("")

    if report["issues"]:
        lines.append("## 问题清单（需核实）")
        lines.append("")
        for i, it in enumerate(report["issues"], 1):
            lv = {"high": "🔴", "mid": "🟡"}.get(it["level"], "⚪")
            lines.append(f"{i}. {lv} **[{it['type']}]** （{it['page']}）{it['detail']}")
        lines.append("")

    fb = report["fact_base"]
    lines.append("## 复核使用的原始数据源")
    lines.append("")
    if fb["anchor_school"]:
        a = fb["anchor_school"]
        lines.append(f"- 锚定学校：**{a['name']}**（{a['province']} {a['level']}）"
                     f"，专业目录 {fb['majors_count']} 条（已核实）")
    lines.append(f"- 全网抓取素材：{fb['raw_items_count']} 条（按主题/学校检索）")
    for it in fb["raw_items"]:
        lines.append(f"  - [{it['scope']}/{it['theme_key']}] {it['title']}")
    lines.append("")
    lines.append("> 复核口径：专业代码/考试科目以数据库专业目录为准；其余事实以全网抓取素材为准。"
                 "凡源数据未提供的精确数字（招生人数/分数线/报录比/学费等）均不得编造。")
    return "\n".join(lines)


def verify_and_write(session, topic, content, out_dir):
    """构建基准→复核→写文件（review.json + review.md）到创作目录，返回报告。"""
    fb = build_fact_base(session, topic)
    report = verify_draft(content, fb)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "review.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "review.md"), "w", encoding="utf-8") as f:
        f.write(_render_md(report, topic, content))
    return report
