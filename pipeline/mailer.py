"""每日邮件推送：把当天各话题的图片打包成独立 zip，一封日报邮件发给指定收件人。

- SMTP 配置来自 .env：SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASS；收件人 MAIL_TO(逗号分隔)。
- 每个话题目录(outputs/cards/<编号>_<主题名>/<YYYYMMDD>_<话题>)打成一个 zip：
  outputs/outbox/<YYYYMMDD>_<话题>.zip，内含 图片 + 发布文案.md + 复核.md。
- 邮件正文总结当天内容：本周计划、各话题标题/页数/复核结论。
"""
import glob
import os
import re
import smtplib
import zipfile
from datetime import date
from email.message import EmailMessage
from email.utils import formataddr

from .config import settings  # noqa: F401  触发 .env 加载

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.qq.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
MAIL_TO = [x.strip() for x in os.getenv("MAIL_TO", "").split(",") if x.strip()]
DEFAULT_RECIPIENTS = ["liujinyanjill@163.com", "454748276@qq.com"]


def today_run_dirs(day=None):
    """列出某日期(默认今天)的所有话题目录：outputs/cards/*/<YYYYMMDD>_*/。"""
    stamp = (date.fromisoformat(day) if isinstance(day, str) else (day or date.today())
             ).strftime("%Y%m%d")
    runs = []
    for theme_dir in sorted(glob.glob(os.path.join(settings.output_dir, "cards", "*"))):
        if not os.path.isdir(theme_dir):
            continue
        for run in sorted(glob.glob(os.path.join(theme_dir, f"{stamp}_*"))):
            if os.path.isdir(run):
                runs.append(run)
    return runs


def package_topic(run_dir, outbox_dir=None):
    """把一个话题目录打成 zip（排除嵌套 zip），返回 zip 路径。"""
    outbox = outbox_dir or os.path.join(settings.output_dir, "outbox")
    os.makedirs(outbox, exist_ok=True)
    folder_name = os.path.basename(run_dir.rstrip("/"))
    zip_path = os.path.join(outbox, f"{folder_name}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(run_dir):
            for fn in sorted(files):
                if fn.endswith(".zip"):
                    continue
                full = os.path.join(root, fn)
                arc = os.path.join(folder_name, os.path.relpath(full, run_dir))
                zf.write(full, arc)
    return zip_path


def _topic_info(run_dir):
    """从话题目录提取 (标题, 复核结论, 图片数)。"""
    title, verdict = "", ""
    doc = os.path.join(run_dir, "发布文案.md")
    if os.path.exists(doc):
        with open(doc, encoding="utf-8") as f:
            for ln in f:
                if ln.startswith("# "):
                    title = ln[2:].strip()
                    break
    review = os.path.join(run_dir, "复核.md")
    if os.path.exists(review):
        txt = open(review, encoding="utf-8").read()
        m = re.search(r"结论[：:]\s*(PASS|NEEDS_REVIEW)", txt)
        verdict = m.group(1) if m else ""
    npng = len(glob.glob(os.path.join(run_dir, "*.png")))
    return title, verdict, npng


def build_summary(day, runs):
    """邮件正文：本周计划 + 各话题标题/页数/复核结论。"""
    from .creator import planner
    stamp = (date.fromisoformat(day) if isinstance(day, str) else (day or date.today())
             ).strftime("%Y-%m-%d")
    plan = planner.plan_for(stamp)
    lines = [
        f"考研内容日报 · {stamp}",
        "",
        f"本周计划：{plan['name']}（{plan['week_start']} ~ {plan['week_end']}）",
        f"本周主题：{'、'.join(plan['themes_cn'])}",
        "",
        f"今日产出 {len(runs)} 篇：",
        "",
    ]
    for run in runs:
        title, verdict, npng = _topic_info(run)
        lines.append(f"- {os.path.basename(run)}｜{title or '—'}｜{npng} 张｜复核：{verdict or '—'}")
    lines += [
        "",
        "各话题图片见附件压缩包（内含 图片 + 发布文案.md + 复核.md），解压后按文件名顺序即翻页顺序。",
        "",
        "-- 自动发送自 dlmu 考研内容流水线",
    ]
    return "\n".join(lines)


def send_report(day=None, recipients=None, dry_run=False, force=False):
    """打包当天所有话题并发送日报邮件。返回结果 dict。

    防重：每个日期只发一次（outputs/outbox/.sent_<YYYYMMDD>.json 标记）；
    重复调用自动跳过，force=True 才允许重发。
    """
    runs = today_run_dirs(day)
    if not runs:
        return {"sent": False, "reason": "当天没有话题产物"}
    stamp = (date.fromisoformat(day) if isinstance(day, str) else (day or date.today())
             ).strftime("%Y%m%d")
    outbox = os.path.join(settings.output_dir, "outbox")
    marker = os.path.join(outbox, f".sent_{stamp}.json")
    if os.path.exists(marker) and not force:
        return {"sent": False, "reason": f"{stamp} 的日报已发送过，跳过重复发送（确需重发加 --force）"}
    zips = [package_topic(r) for r in runs]
    body = build_summary(day, runs)
    to = recipients or MAIL_TO or DEFAULT_RECIPIENTS
    msg = EmailMessage()
    msg["From"] = formataddr(("考研内容流水线", SMTP_USER))
    msg["To"] = ", ".join(to)
    msg["Subject"] = f"考研内容日报 {stamp}（{len(runs)} 篇）"
    msg.set_content(body)
    total = 0
    for z in zips:
        data = open(z, "rb").read()
        total += len(data)
        msg.add_attachment(data, maintype="application", subtype="zip",
                           filename=os.path.basename(z))
    if dry_run:
        return {"sent": False, "dry_run": True, "to": to, "zips": zips,
                "total_bytes": total, "body": body}
    if not (SMTP_USER and SMTP_PASS):
        raise RuntimeError("缺少 SMTP_USER/SMTP_PASS（写入 .env）")
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=120) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)
    import json
    import datetime as _dt
    os.makedirs(outbox, exist_ok=True)
    with open(marker, "w", encoding="utf-8") as f:
        json.dump({"sent_at": _dt.datetime.utcnow().isoformat() + "Z",
                   "to": to, "zips": [os.path.basename(z) for z in zips],
                   "total_bytes": total}, f, ensure_ascii=False, indent=2)
    return {"sent": True, "to": to, "zips": zips, "total_bytes": total}
