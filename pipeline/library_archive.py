"""把当天的话题产物归档成团队资料库图文文档（主题分层）。

目标结构（团队空间 考研内容工作室）：
  图文创作库/<01_院校专业解读>/20261013_双非考…   ← 每话题一个图文文档
      （配图内嵌显示 + 正文文案 + 话题标签 + 复核结论 + zip 附件）
  每日汇总/<YYYY-MM-DD>/内容日报                    ← 当天总结文档

用法：python3 pipeline/library_archive.py <date:YYYY-MM-DD>
"""
import glob
import os
import re
import subprocess
import sys

LIB = ("/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/"
       "resources/plugins/workbuddy-builtin/skills/library")
SPACE_ID = "Z6YZ1A7DvhUGhl5I2BH7hK"
F_CREATION = "ZHsZJxIXZAVeuF3xh6kSqb"   # 图文创作库
F_SUMMARY = "DnDXmkpRjvaZ060YD9FqB9"    # 每日汇总
OUT = "outputs/outbox"


def sh(args):
    r = subprocess.run(args, capture_output=True, text=True, timeout=120)
    return (r.stdout or "") + (r.stderr or "")


def children(parent_id):
    import json
    out = subprocess.run(
        ["python3", f"{LIB}/space_api.py", "space.workspace.list-nodes",
         "--space-id", SPACE_ID, "--parent-node-id", parent_id, "--limit", "100"],
        capture_output=True, text=True, timeout=120).stdout
    try:
        data = json.loads(out[out.index("{"):])
        return {n["title"]: n["id"] for n in data.get("data", {}).get("nodes", [])}
    except Exception:
        return {}


def ensure_folder(title, parent_id):
    """按标题找(或建)子文件夹，返回节点 id。幂等。"""
    ch = children(parent_id)
    if title in ch:
        return ch[title]
    out = sh(["python3", f"{LIB}/manage/create_folder.py", "--title", title,
              "--space-id", SPACE_ID, "--parent-id", parent_id])
    m = re.search(r"KS_FOLDER_CREATE\t(\S+)\t", out)
    return m.group(1) if m else None


def upload_image(path):
    out = sh(["python3", f"{LIB}/manage/upload_image.py", path])
    m = re.search(r'"url":"([^"]+)"', out)
    return m.group(1) if m else None


def parse_doc(run_dir):
    title, body, tags = "", "", ""
    doc = os.path.join(run_dir, "发布文案.md")
    if os.path.exists(doc):
        lines = open(doc, encoding="utf-8").read().splitlines()
        section = ""
        buf = {"body": [], "tags": []}
        for ln in lines:
            if ln.startswith("# ") and not title:
                title = ln[2:].strip()
                continue
            if ln.startswith("## "):
                section = ln
                continue
            if "② 正文" in section:
                buf["body"].append(ln)
            elif "③ 话题标签" in section:
                buf["tags"].append(ln)
        body = "\n".join(buf["body"]).strip()
        tags = " ".join(x.strip() for x in buf["tags"] if x.strip().startswith("#"))
    verdict = ""
    review = os.path.join(run_dir, "复核.md")
    if os.path.exists(review):
        m = re.search(r"结论[：:]\s*(PASS|NEEDS_REVIEW)",
                      open(review, encoding="utf-8").read())
        verdict = m.group(1) if m else ""
    return title, body, tags, verdict


def _norm(s):
    """标题归一化：只留中文/字母/数字，用于同话题防重（新旧命名都能对上）。"""
    return re.sub(r"[^\u4e00-\u9fff0-9A-Za-z]", "", str(s))


def build_doc(run_dir, theme_dir_name):
    """一个话题 → 图文创作库/<主题>/<YYYYMMDD_话题> 图文文档（幂等：已归档则跳过）。"""
    name = os.path.basename(run_dir.rstrip("/"))
    theme_folder = ensure_folder(theme_dir_name, F_CREATION)
    if not theme_folder:
        return {"name": name, "error": f"主题文件夹 {theme_dir_name} 创建失败"}
    label = _norm(name.split("_", 1)[1]) if "_" in name else _norm(name)
    ch = children(theme_folder)
    existing = next((nid for t, nid in ch.items() if _norm(t) == label or label in _norm(t)), None)
    if existing:
        return {"name": name, "node_id": existing, "skipped": True,
                "title": next(t for t, nid in ch.items() if nid == existing)}
    title, body, tags, verdict = parse_doc(run_dir)
    pngs = sorted(glob.glob(os.path.join(run_dir, "*.png")))
    md = [f"# {title or name}", "",
          f"> {name} ｜ 配图 {len(pngs)} 张 ｜ 复核：**{verdict or '—'}**", ""]
    md += ["## 配图（按序号即翻页顺序）", ""]
    for p in pngs:
        url = upload_image(p)
        if not url:
            md += [f"- ⚠️ {os.path.basename(p)} 上传失败", ""]
            continue
        md += [f"![{os.path.basename(p)}]({url})", ""]
    if body:
        md += ["## 正文", "", body, ""]
    if tags:
        md += ["## 话题标签", "", tags, ""]
    md += ["## 复核结论", "", verdict or "—", ""]
    tmp_md = "/tmp/_topic_doc.md"
    open(tmp_md, "w", encoding="utf-8").write("\n".join(md))
    out = sh(["python3", f"{LIB}/doc/create_doc.py", "--title", name,
              "--space-id", SPACE_ID, "--parent-id", theme_folder,
              "--content-file", tmp_md])
    m = re.search(r"KS_DOC_CREATE\t(\S+)\t", out)
    node_id = m.group(1) if m else None
    link = re.search(r"https://www\.workbuddy\.cn/space/d/\S+", out)
    atts = 0
    if node_id:
        for z in glob.glob(os.path.join(OUT, name + ".zip")):
            sh(["python3", f"{LIB}/attachment/attachment.py", "upload",
                "--node-id", node_id, "--path", os.path.abspath(z)])
            atts += 1
    return {"name": name, "title": title, "images": len(pngs),
            "node_id": node_id, "link": link.group(0) if link else None,
            "verdict": verdict, "atts": atts}


def build_summary_doc(day, runs):
    """每日汇总/<日期>/内容日报：当天总结文档（同日重复执行=覆盖更新）。"""
    try:
        from . import mailer
    except ImportError:   # 直接以脚本方式运行时
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from pipeline import mailer
    stamp = day.replace("-", "")
    date_folder = ensure_folder(day, F_SUMMARY)
    if not date_folder:
        return {"error": "每日汇总日期文件夹创建失败"}
    md = mailer.build_summary(day, runs)
    tmp = "/tmp/_daily_summary.md"
    open(tmp, "w", encoding="utf-8").write(md)
    doc_title = "内容日报"
    ch = children(date_folder)
    if doc_title in ch:   # 已存在 → 全量覆盖
        out = sh(["python3", f"{LIB}/doc/create_doc.py",
                  "--node-block-id", ch[doc_title], "--space-id", SPACE_ID,
                  "--confirm-overwrite", "--content-file", tmp])
    else:
        out = sh(["python3", f"{LIB}/doc/create_doc.py", "--title", doc_title,
                  "--space-id", SPACE_ID, "--parent-id", date_folder,
                  "--content-file", tmp])
    link = re.search(r"https://www\.workbuddy\.cn/space/d/\S+", out)
    return {"link": link.group(0) if link else None}


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else ""
    if not day:
        print("ERROR: 需要日期参数 YYYY-MM-DD")
        return
    stamp = day.replace("-", "")
    runs = [d for d in sorted(glob.glob(f"outputs/cards/*/{stamp}_*"))
            if os.path.isdir(d)]
    if not runs:
        print(f"当天({day})没有话题产物，跳过归档")
        return
    results = []
    for run in runs:
        theme_dir = os.path.basename(os.path.dirname(run.rstrip("/")))
        r = build_doc(run, theme_dir)
        results.append(r)
        print(f"OK {r['name']} | 图{r.get('images', 0)} | {r.get('link')}")
    s = build_summary_doc(day, runs)
    print(f"每日汇总: {s.get('link') or s.get('error')}")
    fails = [r for r in results if not r["node_id"]]
    print(f"\n完成 {len(results) - len(fails)}/{len(results)}；失败 {len(fails)}")


if __name__ == "__main__":
    main()
