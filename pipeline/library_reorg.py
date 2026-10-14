"""资料库层级整理（幂等）：按 主题→话题 分层，可重复执行。

目标结构（团队空间 考研内容工作室 Z6YZ1A7DvhUGhl5I2BH7hK）：
  图文创作库/<01_院校专业解读>/<YYYYMMDD_话题> 图文文档
  采集素材库/<01_院校专业解读>/素材库 · <主题> 文档
  每日汇总/<YYYY-MM-DD>/ 日报汇总文档(+zip)
用法：python3 pipeline/library_reorg.py
"""
import json
import os
import subprocess

LIB = ("/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/"
       "resources/plugins/workbuddy-builtin/skills/library")
SPACE = "Z6YZ1A7DvhUGhl5I2BH7hK"
F_DAILY_OLD = "TndI3udmNngQfIt30UsKPT"   # 旧「考研内容日报」
F_MATERIAL = "H9aDbACBkqapqahQOKA0EN"    # 采集素材库
F_CREATION = "ZHsZJxIXZAVeuF3xh6kSqb"    # 图文创作库
F_SUMMARY = "DnDXmkpRjvaZ060YD9FqB9"     # 每日汇总


def sh(args):
    r = subprocess.run(args, capture_output=True, text=True, timeout=120)
    return (r.stdout or "") + (r.stderr or "")


def children(parent_id):
    out = subprocess.run(
        ["python3", f"{LIB}/space_api.py", "space.workspace.list-nodes",
         "--space-id", SPACE, "--parent-node-id", parent_id, "--limit", "100"],
        capture_output=True, text=True, timeout=120).stdout
    try:
        data = json.loads(out[out.index("{"):])
        return {n["title"]: n["id"] for n in data.get("data", {}).get("nodes", [])}
    except Exception:
        return {}


def ensure_folder(title, parent_id):
    ch = children(parent_id)
    if title in ch:
        return ch[title]
    out = subprocess.run(
        ["python3", f"{LIB}/manage/create_folder.py", "--title", title,
         "--space-id", SPACE, "--parent-id", parent_id],
        capture_output=True, text=True, timeout=120).stdout
    import re
    m = re.search(r"KS_FOLDER_CREATE\t(\S+)\t", out)
    return m.group(1) if m else None


def move(node_id, parent_id):
    subprocess.run(["python3", f"{LIB}/space_api.py", "space.workspace.move-node",
                    "--node-id", node_id, "--target-parent-id", parent_id],
                   capture_output=True, text=True, timeout=120)


def main():
    from .storage import session_scope, Draft, Topic

    # 1) 12 个主题文件夹：先在旧日报目录下找(昨天误建)，挪到 图文创作库；缺的补建
    old_ch = children(F_DAILY_OLD)
    creation_ch = children(F_CREATION)
    theme_folders = {}
    for title, nid in old_ch.items():
        if title[0].isdigit() and "_" in title and not title.startswith("20"):
            if title not in creation_ch:
                move(nid, F_CREATION)
            theme_folders[title] = creation_ch.get(title) or nid
    for title in sorted(theme_folders):
        if title not in children(F_CREATION):
            nid = ensure_folder(title, F_CREATION)
            theme_folders[title] = nid or theme_folders[title]

    # 2) 采集素材库：建主题子文件夹 + 基础数据
    mat_ch = children(F_MATERIAL)
    mat_folders = {}
    for title, nid in mat_ch.items():
        if title.startswith("素材库 · "):
            cn = title.replace("素材库 · ", "")
            folder_title = next((t for t in old_ch if t.endswith(cn) and t[0].isdigit()),
                                "基础数据" if cn == "基础数据" else cn)
            if folder_title not in mat_ch:
                nid2 = ensure_folder(folder_title, F_MATERIAL)
            else:
                nid2 = mat_ch[folder_title]
            mat_folders[cn] = nid2
    base_f = ensure_folder("基础数据", F_MATERIAL)
    mat_folders.setdefault("基础数据", base_f)

    # 3) 旧日报目录下的日期文件夹 → 每日汇总；话题文档 → 图文创作库/<主题>
    summary_ch = children(F_SUMMARY)
    for title, nid in old_ch.items():
        if title.startswith("20") and "-" in title:      # 日期文件夹(含汇总文档+zip)
            if title not in summary_ch:
                move(nid, F_SUMMARY)
    # 话题文档：按草稿标题→主题 映射
    title2theme = {}
    with session_scope() as session:
        rows = (session.query(Draft.title, Topic.theme_id)
                .join(Topic, Topic.id == Draft.topic_id).all())
        from .storage import Theme
        names = {t.id: t.name for t in session.query(Theme).all()}
        for dtitle, tid in rows:
            nm = names.get(tid)
            if nm:
                for t in old_ch:
                    if t[0].isdigit() and "_" in t and t.split("_", 1)[1] == nm:
                        title2theme[dtitle] = t
    for date_folder in [t for t in summary_ch]:
        pass
    # 重新列出日期文件夹(已在每日汇总下)与旧位置的文档
    for dch in [children(F_SUMMARY), old_ch]:
        for fname, fid in dch.items():
            if not (fname.startswith("20") and "-" in fname):
                continue
            for doc_title, doc_id in children(fid).items():
                theme_folder = title2theme.get(doc_title)
                if theme_folder and theme_folder in theme_folders:
                    move(doc_id, theme_folders[theme_folder])
                    print(f"moved doc -> {theme_folder}: {doc_title[:30]}")

    # 4) 素材库文档 → 采集素材库/<主题文件夹>
    for doc_title, doc_id in children(F_MATERIAL).items():
        if not doc_title.startswith("素材库 · "):
            continue
        cn = doc_title.replace("素材库 · ", "")
        target = mat_folders.get(cn) or mat_folders.get("基础数据")
        if target and doc_id != target:
            move(doc_id, target)
            print(f"moved material -> {cn}")

    print("整理完成：")
    print("  图文创作库子目录:", sorted(children(F_CREATION)))
    print("  采集素材库子目录:", sorted(children(F_MATERIAL)))
    print("  每日汇总子目录:", sorted(children(F_SUMMARY)))
    print("  旧考研内容日报剩余:", sorted(children(F_DAILY_OLD)))


if __name__ == "__main__":
    main()
