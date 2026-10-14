"""采集素材库 ↔ 团队资料库 双向同步。

- sync-to（默认）：把本地 SQLite raw_items 按主题镜像成资料库文档（每主题一篇，
  按日期分节：标题+正文+原文链接），团队可浏览、复核报告可引用、跨电脑可访问。
- sync-from（--from-library）：把资料库里各主题文档读回本地 SQLite（按标题/URL 去重），
  实现「换一台电脑也能取数据生成文案」。

资料库结构：团队空间「考研内容工作室」→ 文件夹「采集素材库」→ 素材库 · <主题名>(每主题一篇)。
主题→文档节点 的映射存在 outputs/library_docs.json（新机器首跑会按标题搜索找回或新建）。
"""
import glob
import json
import os
import re
import subprocess
from datetime import datetime

from .config import settings  # noqa: F401  触发 .env 加载
from .storage import repo, session_scope

LIB = ("/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/"
       "resources/plugins/workbuddy-builtin/skills/library")
SPACE_ID = "Z6YZ1A7DvhUGhl5I2BH7hK"          # 团队空间「考研内容工作室」
FOLDER_TITLE = "采集素材库"
MAP_PATH = os.path.join(settings.output_dir, "library_docs.json")
THEME_CN_FALLBACK = {"_base": "基础数据"}


def _sh(args, timeout=120):
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    return (r.stdout or "") + (r.stderr or "")


def _load_map():
    if os.path.exists(MAP_PATH):
        try:
            return json.load(open(MAP_PATH, encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_map(m):
    os.makedirs(os.path.dirname(MAP_PATH), exist_ok=True)
    json.dump(m, open(MAP_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def _find_node_by_title(title):
    """按标题搜索节点，返回 (node_id, kind) 或 None。"""
    out = _sh(["python3", f"{LIB}/space_api.py", "space.searcher.search-nodes",
               "--query", title, "--size", "10"])
    try:
        data = json.loads(out[out.index("{"):])
    except Exception:
        return None
    for n in (data.get("data", {}).get("nodes")
              or data.get("data", {}).get("results") or []):
        if n.get("title") == title and n.get("spaceId", SPACE_ID) == SPACE_ID:
            return n.get("nodeId") or n.get("nodeBlockId") or n.get("id")
    return None


def _ensure_folder(m):
    """确保「采集素材库」文件夹存在（有映射→校验；无→搜索→新建）。"""
    fid = m.get("folder")
    if fid:
        info = _sh(["python3", f"{LIB}/space_api.py", "space.workspace.node-info",
                    "--node-id", fid])
        if '"kind":"folder"' in info.replace(" ", "") or '"kind": "folder"' in info:
            return fid
    fid = _find_node_by_title(FOLDER_TITLE)
    if not fid:
        out = _sh(["python3", f"{LIB}/manage/create_folder.py",
                   "--title", FOLDER_TITLE, "--space-id", SPACE_ID])
        mm = re.search(r"KS_FOLDER_CREATE\t(\S+)\t", out)
        fid = mm.group(1) if mm else None
    if fid:
        m["folder"] = fid
        _save_map(m)
    return fid


def _theme_doc_title(theme_key, theme_name):
    return f"素材库 · {THEME_CN_FALLBACK.get(theme_key, theme_name or theme_key)}"


def _ensure_theme_doc(m, folder_id, theme_key, theme_name):
    """取(或建)某主题的素材库文档节点。"""
    docs = m.setdefault("themes", {})
    node = docs.get(theme_key)
    if node:
        info = _sh(["python3", f"{LIB}/space_api.py", "space.workspace.node-info",
                    "--node-id", node])
        if '"kind":"doc"' in info.replace(" ", "") or '"kind": "doc"' in info:
            return node
    title = _theme_doc_title(theme_key, theme_name)
    node = _find_node_by_title(title)
    if not node:
        out = _sh(["python3", f"{LIB}/doc/create_doc.py",
                   "--title", title, "--space-id", SPACE_ID,
                   "--parent-id", folder_id,
                   "--content", f"# {title}\n\n> 由流水线自动维护，请勿手工编辑。"])
        mm = re.search(r"KS_DOC_CREATE\t(\S+)\t", out)
        node = mm.group(1) if mm else None
    if node:
        docs[theme_key] = node
        _save_map(m)
    return node


def build_theme_md(items, theme_key, theme_name):
    title = _theme_doc_title(theme_key, theme_name)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    lines = [f"# {title}", "",
             f"> 共 {len(items)} 条 ｜ 更新(UTC)：{now} ｜ 由流水线自动同步，请勿手工编辑。",
             "",
             "分节格式：`## [日期] 标题`，节内含 scope 与原文链接，供复核引用与换机恢复。", ""]
    for it in items:  # 旧→新
        fa = it.fetched_at
        day = fa.strftime("%Y-%m-%d") if hasattr(fa, "strftime") else str(fa or "")[:10]
        url = it.url or ""
        lines += [f"## [{day}] {it.title}",
                  f"- scope：{it.scope or '—'} ｜ 原文：{url or '—'}",
                  "",
                  (it.content or "").strip(),
                  ""]
    return "\n".join(lines)


def sync_to():
    """本地 SQLite → 资料库（每主题一篇，全量覆盖更新）。"""
    m = _load_map()
    folder = _ensure_folder(m)
    if not folder:
        return {"ok": False, "error": "采集素材库文件夹创建失败"}
    done, failed = [], []
    with session_scope() as session:
        from .storage import RawItem
        themes = {t.key: t.name for t in repo.active_themes(session)}
        groups = {}
        for it in (session.query(RawItem)
                   .order_by(RawItem.fetched_at.asc()).limit(2000).all()):
            groups.setdefault(it.theme_key or "_base", []).append(it)
    for key, items in groups.items():
        name = themes.get(key, THEME_CN_FALLBACK.get(key, key))
        node = _ensure_theme_doc(m, folder, key, name)
        if not node:
            failed.append(key)
            continue
        md = build_theme_md(items, key, name)
        tmp = "/tmp/_lib_sync.md"
        open(tmp, "w", encoding="utf-8").write(md)
        out = _sh(["python3", f"{LIB}/doc/create_doc.py",
                   "--node-block-id", node, "--space-id", SPACE_ID,
                   "--confirm-overwrite", "--content-file", tmp], timeout=180)
        (done if "KS_DOC_CREATE" in out or "KS_USER_REPLY" in out else failed).append(
            {"theme": key, "items": len(items), "node": node})
    return {"ok": True, "synced": done, "failed": failed,
            "links": {k: f"https://www.workbuddy.cn/space/d/{v}"
                      for k, v in m.get("themes", {}).items()}}


def _strip_tags(x):
    return re.sub(r"\n{2,}", "\n", re.sub(r"<[^>]+>", "\n", x)).strip()


_MD_ESC = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|])")


def _unescape_md(x):
    """资料库会把 markdown 特殊字符转义存储(如 \\[)，读回时还原。"""
    return _MD_ESC.sub(r"\1", x)


def _parse_doc_sections(out):
    """解析 get_doc_reviews 输出（XML 块结构），返回 [{day,title,url,scope,content}]。"""
    lines = [ln for ln in out.splitlines() if not ln.startswith("KS_")]
    xml = "\n".join(lines)
    xml = re.sub(r"^---\n.*?\n---\n", "", xml, flags=re.S)   # 去 front-matter
    sections = []
    for part in re.split(r'<Heading[^>]*level="2"[^>]*>', xml)[1:]:
        head_xml, _, body_xml = part.partition("</Heading>")
        head = _unescape_md(_strip_tags(head_xml).replace("\n", " ").strip())
        m = re.match(r"\[([\d-]+)\]\s*(.+)", head, re.S)
        if not m:
            continue
        day, sec_title = m.group(1), m.group(2).strip()
        text = _unescape_md(_strip_tags(body_xml))
        url_m = re.search(r"原文：(\S+)", text)
        scope_m = re.search(r"scope：(\S+)", text)
        body = re.sub(r"^.*scope：.*$", "", text, flags=re.M).strip()
        if not sec_title:
            continue
        sections.append({
            "day": day, "title": sec_title,
            "url": url_m.group(1) if url_m and url_m.group(1) != "—" else None,
            "scope": scope_m.group(1) if scope_m else None,
            "content": body,
        })
    return sections


def sync_from():
    """资料库 → 本地 SQLite（换机恢复：按分节解析读回，去重入库）。"""
    m = _load_map()
    restored, new = 0, 0
    for theme_key, node in m.get("themes", {}).items():
        out = _sh(["python3", f"{LIB}/doc/get_doc_reviews.py",
                   "--page-id", node], timeout=180)
        if "KS_DOC_REVIEWS" not in out:
            continue
        for sec in _parse_doc_sections(out):
            restored += 1
            with session_scope() as session:
                _, created = repo.add_raw_item(
                    session, title=sec["title"], kind="web",
                    content=sec["content"], url=sec["url"],
                    theme_key=(None if theme_key == "_base" else theme_key),
                    scope=sec["scope"], source_id=None)
                if created:
                    new += 1
    return {"restored_sections": restored, "new_items": new}


def library_links():
    """theme_key → 资料库文档链接（供复核报告引用）。"""
    m = _load_map()
    return {k: f"https://www.workbuddy.cn/space/d/{v}"
            for k, v in m.get("themes", {}).items()}
