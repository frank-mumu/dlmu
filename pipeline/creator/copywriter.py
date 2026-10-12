"""文案生成：优先调 LLM（OpenAI 兼容），无 key / 调用失败时降级到模板，保证链路可跑通。"""
import requests

from ..config import settings

_XHS_SYSTEM = ("你是资深考研自媒体运营，擅长写小红书爆款图文笔记："
               "标题吸睛、干货密集、分段清晰、善用 emoji 与话题标签。")


def write(topic, school=None, majors=None, raw_items=None):
    """返回 dict(title, body, tags, generator[, note])。"""
    if settings.llm_ready:
        try:
            return _write_with_llm(topic, school, majors, raw_items)
        except Exception as exc:  # 降级，不阻断流水线
            result = _write_with_template(topic, school, majors)
            result["note"] = f"LLM 调用失败，已降级模板: {exc}"
            return result
    return _write_with_template(topic, school, majors)


def _llm_chat(messages, temperature=0.7, max_tokens=1200):
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {settings.llm_api_key}",
               "Content-Type": "application/json"}
    payload = {"model": settings.llm_model, "messages": messages,
               "temperature": temperature, "max_tokens": max_tokens}
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _write_with_llm(topic, school, majors, raw_items):
    ctx = _context_text(topic, school, majors, raw_items)
    user = (f"请基于以下考研素材，写一篇小红书图文笔记。\n"
            f"选题：{topic.title}\n素材：\n{ctx}\n\n"
            f"严格按此格式输出：\n标题：<不超过20字>\n正文：<分段干货，可用emoji>\n"
            f"标签：<3-6个，每个以#开头，空格分隔>")
    text = _llm_chat([
        {"role": "system", "content": _XHS_SYSTEM},
        {"role": "user", "content": user}])
    return _parse(text)


def _parse(text):
    title, mode, buf, tags = "", None, [], []
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("标题："):
            title = s[len("标题："):].strip(); mode = "title"
        elif s.startswith("正文："):
            mode = "body"; buf.append(s[len("正文："):].strip())
        elif s.startswith("标签："):
            mode = "tags"; tags = _tags(s[len("标签："):])
        elif mode == "body":
            buf.append(s)
        elif mode == "tags":
            tags += _tags(s)
    body = "\n".join(b for b in buf if b).strip()
    if not title:
        title = (text.splitlines()[0] if text else "考研干货")[:20]
    if not tags:
        tags = ["#考研", "#26考研", "#考研资讯"]
    return {"title": title, "body": body or text.strip(), "tags": tags, "generator": "llm"}


def _tags(s):
    return [t for t in s.replace("，", " ").replace(",", " ").split() if t.startswith("#")]


def _context_text(topic, school, majors, raw_items):
    parts = []
    if school:
        parts.append(f"学校：{school.name}（{school.province or ''} {school.level or ''}）")
    for m in (majors or [])[:12]:
        parts.append(f"- {m.degree_type} {m.name}（{m.code}）方向:{m.direction or '-'} "
                     f"科目:{m.exam_subjects or '-'}")
    for it in (raw_items or [])[:3]:
        parts.append(f"[{it.title}] {it.content or ''}")
    return "\n".join(parts) if parts else (topic.rationale or topic.title)


def _write_with_template(topic, school, majors):
    if school and topic.kind == "school":
        title = f"{school.name}考研｜26硕士招生速览"
        lines = [f"📚 {school.name}（{school.province or ''}{school.level or ''}）2026 硕士招生看点", ""]
        if majors:
            lines.append("🔹 热门专业方向：")
            lines += [f"· {m.degree_type} {m.name}（{m.code}）" for m in majors[:8]]
            lines += ["", "🔹 报考小提示：",
                      "· 以学校研究生院官网最新招生简章为准",
                      "· 关注考试科目与参考书变化",
                      "· 结合报录比与复试线理性选择"]
        else:
            lines.append("🔹 具体专业目录以研招网/官网为准")
        body = "\n".join(lines)
        tags = ["#考研", "#26考研", school.name, "#招生简章", "#考研资讯"]
    else:
        title = "本周研招网硕士目录更新速览"
        body = ("📢 近期研招网硕士目录有多所学校更新\n\n"
                "🔹 建议同学们：\n· 及时核对目标专业考试科目\n· 关注新增/撤销专业\n"
                "· 以官方简章为最终依据\n\n"
                "（模板占位内容，接入大模型后将自动生成正式文案）")
        tags = ["#考研", "#26考研", "#研招网", "#考研资讯"]
    return {"title": title, "body": body, "tags": tags, "generator": "template"}
