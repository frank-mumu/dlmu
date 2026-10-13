"""把当天的话题产物归档成资料库图文文档：配图内嵌 + 文案 + 复核 + zip 附件。

用法：python3 build_topic_docs.py <date:YYYY-MM-DD> [topic_dir ...]
不传 topic_dir 则处理该日期全部话题；--limit N 只处理前 N 个。
"""
import glob
import os
import re
import subprocess
import sys

LIB = ("/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/"
       "resources/plugins/workbuddy-builtin/skills/library")
SPACE_ID = "Z6YZ1A7DvhUGhl5I2BH7hK"
DATE_FOLDER = {"2026-10-13": "tvLUfc5u47yQIshMLmsqNV"}  # 日期 -> 资料库日期文件夹节点
OUT = "outputs/outbox"


def sh(args):
    r = subprocess.run(args, capture_output=True, text=True, timeout=120)
    return (r.stdout or "") + (r.stderr or "")


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


def build_doc(run_dir, parent_id):
    name = os.path.basename(run_dir.rstrip("/"))
    title, body, tags, verdict = parse_doc(run_dir)
    pngs = sorted(glob.glob(os.path.join(run_dir, "*.png")))
    md = [f"# {title or name}", "",
          f"> 主题目录：{name} ｜ 配图 {len(pngs)} 张 ｜ 复核：**{verdict or '—'}**", ""]
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
    out = sh(["python3", f"{LIB}/doc/create_doc.py", "--title", title or name,
              "--space-id", SPACE_ID, "--parent-id", parent_id,
              "--content-file", tmp_md])
    m = re.search(r"KS_DOC_CREATE\t(\S+)\t", out)
    node_id = m.group(1) if m else None
    link = re.search(r"https://www\.workbuddy\.cn/space/d/\S+", out)
    if node_id:
        zips = glob.glob(os.path.join(OUT, name + ".zip"))
        for z in zips:
            sh(["python3", f"{LIB}/attachment/attachment.py", "upload",
                "--node-id", node_id, "--path", os.path.abspath(z)])
    return {"name": name, "title": title, "images": len(pngs),
            "node_id": node_id, "link": link.group(0) if link else None,
            "verdict": verdict}


def ensure_date_folder(day):
    """取(或建)某日期在资料库的日期文件夹节点，并缓存到 DATE_FOLDER。"""
    parent = DATE_FOLDER.get(day)
    if parent:
        return parent
    out = sh(["python3", f"{LIB}/manage/create_folder.py", "--title", day,
              "--space-id", SPACE_ID, "--parent-id", "TndI3udmNngQfIt30UsKPT"])
    m = re.search(r"KS_FOLDER_CREATE\t(\S+)\t", out)
    if not m:
        return None
    DATE_FOLDER[day] = m.group(1)
    return DATE_FOLDER[day]


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else ""
    parent = ensure_date_folder(day)
    if not parent:
        print(f"ERROR: 日期文件夹 {day} 创建失败")
        return
    stamp = day.replace("-", "")
    runs = [d for d in sorted(glob.glob(f"outputs/cards/*/{stamp}_*"))
            if os.path.isdir(d)]
    results = []
    for run in runs:
        r = build_doc(run, parent)
        results.append(r)
        print(f"OK {r['name']} | 图{r['images']} | {r['link']}")
    fails = [r for r in results if not r["node_id"]]
    print(f"\n完成 {len(results) - len(fails)}/{len(results)}；失败 {len(fails)}")


if __name__ == "__main__":
    main()
