"""命令行入口：init-db / seed-themes / fetch / fetch-all / ingest-web / create / select / save-draft / list-drafts / publish。"""
import argparse
import json
import os

from .config import settings
from .creator import run as create_run
from .creator import themes as theme_mod
from .fetchers import fetch_all, get_fetcher
from .storage import init_db, repo, session_scope, Topic


def cmd_init_db(_args):
    init_db()
    with session_scope() as session:
        theme_mod.seed_themes(session)
        n = len(repo.active_themes(session))
    print(f"[init-db] 已建表 -> {settings.database_url}；已 seed {n} 个主题")


def cmd_seed_themes(_args):
    with session_scope() as session:
        theme_mod.seed_themes(session)
        n = len(repo.active_themes(session))
    print(f"[seed-themes] 已写入/更新 {n} 个主题")


def cmd_list_themes(_args):
    with session_scope() as session:
        for t in repo.active_themes(session):
            print(f"{t.id}\t{t.key}\t{t.scope}\t{t.audience}\t{t.name}\t{t.description or ''}")
        print("（格式：id\\tkey\\tscope\\taudience\\tname\\tdescription）")


def cmd_fetch(args):
    options = {"pool": args.pool or settings.default_pool}
    if args.path:
        options["path"] = args.path
    if args.url:
        options["feed_url"] = args.url
    fetcher = get_fetcher(args.source, **options)
    with session_scope() as session:
        stats = fetcher.run(session)
    print(f"[fetch:{args.source}] {stats}")


def cmd_fetch_all(_args):
    with session_scope() as session:
        stats = fetch_all(session, school_names=settings.default_pool or None)
    print("[fetch-all]")
    for k, v in stats.items():
        print(f"  - {k}: {v}")


def cmd_ingest_web(args):
    """把 Agent 全网检索到的内容批量入库（打 theme_key/scope 标签），供创作检索。"""
    with open(args.file, encoding="utf-8") as f:
        items = json.load(f)
    with session_scope() as session:
        new = 0
        for it in items:
            _, created = repo.add_raw_item(
                session, title=it["title"], kind=it.get("kind", "web"),
                content=it.get("content"), url=it.get("url"),
                theme_key=it.get("theme_key"), scope=it.get("scope"),
                source_id=None)
            if created:
                new += 1
    print(f"[ingest-web] 共 {len(items)} 条，新增 {new} 条")


def cmd_create(args):
    print(f"[create] {create_run(limit=args.limit, period=args.period)}")


def cmd_select(args):
    from .creator import runner
    theme_keys = None
    if args.week:
        from .creator import planner
        theme_keys = planner.plan_for().get("theme_keys")
        plan = planner.plan_for()
        print(f"[select] 周计划={plan['name']}（{plan['week_start']}~{plan['week_end']}）"
              f" 主题：{'、'.join(plan['themes_cn'])}")
    with session_scope() as session:
        brief = runner.topics_brief(session, limit=args.limit,
                                     period=args.period, theme_id=args.theme,
                                     theme_keys=theme_keys)
    text = json.dumps(brief, ensure_ascii=False, indent=2)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"[select] {len(brief)} 个选题已写入 {args.out}")
    else:
        print(text)


def cmd_save_draft(args):
    from .creator import runner
    with open(args.file, encoding="utf-8") as f:
        drafts = json.load(f)
    result = runner.run_agent(drafts)
    print("[save-draft] " + json.dumps(result, ensure_ascii=False))


def cmd_list_drafts(args):
    with session_scope() as session:
        drafts = repo.list_drafts(session, status=args.status, limit=args.limit)
        for d in drafts:
            print(f"#{d.id} [{d.status}] ({d.generator}) {d.title}  cards={len(d.assets)}")
        if not drafts:
            print("（无草稿）")


def cmd_publish(_args):
    print("[publish] Phase 2 预留：当前请手动导出发布。"
          "approved 草稿可用 `list-drafts --status approved` 查看。")


def cmd_export(args):
    """为已有草稿重新生成「发布文案.md」（标题/正文/话题标签/配图顺序/口播稿），便于复制到平台。"""
    from .creator import narrator, publisher
    with session_scope() as session:
        if args.topic:
            try:
                topic = session.get(Topic, int(args.topic))
            except (ValueError, TypeError):
                topic = None
                for t in session.query(Topic).all():
                    nm = (t.theme.name if t.theme else "") or t.title or ""
                    if args.topic in nm or args.topic == (t.theme.key if t.theme else ""):
                        topic = t
                        break
            drafts = [repo.latest_draft(session, topic.id)] if topic else []
            drafts = [d for d in drafts if d]
        else:
            drafts = repo.list_drafts(session, status=args.status, limit=args.limit)
        n = 0
        for d in drafts:
            if not d.assets:
                continue
            out_dir = os.path.dirname(d.assets[0])
            audio = None
            for ext in ("语音解说.mp3", "语音解说.m4a"):
                p = os.path.join(out_dir, ext)
                if os.path.exists(p):
                    audio = p
                    break
            narration = narrator.build_narration({"title": d.title, "pages": d.pages or []})
            path = publisher.render_publish_doc(
                {"title": d.title, "body": d.body, "tags": d.tags or []},
                out_dir, assets=d.assets, audio=audio, narration=narration)
            n += 1
            print(f"[export] {d.title} -> {path}")
        print(f"[export] 共生成 {n} 份发布文案")


def cmd_verify(args):
    from .creator import runner, verifier
    with session_scope() as session:
        # 支持按 id 或「主题名 / 主题 key」定位 topic
        topic = None
        try:
            topic = session.get(Topic, int(args.topic))
        except (ValueError, TypeError):
            for t in session.query(Topic).all():
                nm = (t.theme.name if t.theme else "") or t.title or ""
                key = (t.theme.key if t.theme else "") or ""
                if args.topic in (nm, key) or args.topic in nm:
                    topic = t
                    break
        if topic is None:
            print(f"[verify] 找不到 topic：{args.topic}（可用 id 或 主题名/key，"
                  f"如 `院校专业解读`）")
            return
        draft = repo.latest_draft(session, topic.id)
        if draft is None:
            print(f"[verify] topic {topic.id}（{topic.title}）尚无草稿，无法复核")
            return
        content = {"title": draft.title, "subtitle": "", "pages": draft.pages or [],
                   "closing": "", "tags": draft.tags or []}
        # 复核报告写回该期的卡片目录（与图片同目录）；无图片时退到主题根目录
        out_dir = (os.path.dirname(draft.assets[0]) if draft.assets
                   else runner.topic_run_dir(session, topic, draft.title))
        report = verifier.verify_and_write(session, topic, content, out_dir)
        print(f"[verify] topic{topic.id}（{topic.theme.name if topic.theme else topic.title}）"
              f" 结论={report['verdict']} "
              f"问题={report['counts']['total']}（高{report['counts']['high']}/中{report['counts']['mid']}）")
        print(f"          报告 -> {os.path.join(out_dir, '复核.md')}")


def cmd_narrate(args):
    """为已有草稿重新生成语音解说 mp3（用当前 TTS_PROVIDER/音色），不重渲图片。"""
    from .creator import narrator
    with session_scope() as session:
        if args.topic:
            try:
                topic = session.get(Topic, int(args.topic))
            except (ValueError, TypeError):
                topic = None
                for t in session.query(Topic).all():
                    nm = (t.theme.name if t.theme else "") or t.title or ""
                    if args.topic in nm or args.topic == (t.theme.key if t.theme else ""):
                        topic = t
                        break
            drafts = [repo.latest_draft(session, topic.id)] if topic else []
            drafts = [d for d in drafts if d]
        else:
            drafts = repo.list_drafts(session, status=args.status, limit=args.limit)
        n = 0
        for d in drafts:
            if not d.assets:
                continue
            out_dir = os.path.dirname(d.assets[0])
            content = {"title": d.title, "pages": d.pages or []}
            narration = narrator.build_narration(content)
            audio = narrator.synthesize(narration, os.path.join(out_dir, "语音解说.mp3"))
            if audio:
                # 同步刷新发布文档：写入口播稿 + 配音文件引用
                publisher.render_publish_doc(
                    {"title": d.title, "body": d.body, "tags": d.tags or []},
                    out_dir, assets=d.assets, audio=audio, narration=narration)
                n += 1
                print(f"[narrate] {d.title} -> {audio}")
        print(f"[narrate] 共生成 {n} 条语音解说（provider={narrator.TTS_PROVIDER}）")


def cmd_clone_voice(args):
    """用录音做 ElevenLabs 即时克隆音色，返回 voice_id；--save 写入 .env 并启用。"""
    from .creator import narrator
    vid = narrator.clone_voice(args.name, args.file)
    print(f"[clone-voice] name={args.name} voice_id={vid}")
    if args.save:
        with open(".env", "a", encoding="utf-8") as f:
            f.write(f"\nELEVENLABS_VOICE_ID={vid}\nTTS_PROVIDER=elevenlabs\n")
        print("[clone-voice] 已写入 .env：ELEVENLABS_VOICE_ID + TTS_PROVIDER=elevenlabs"
              "（重跑创作/export 即用克隆音色）")


def cmd_plan(args):
    """查看内容周计划（本周起 n 周），可写入 markdown 供查阅。"""
    from .creator import planner
    text = planner.render_markdown(n=args.weeks)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"[plan] 周计划已写入 {args.out}")
    print(text)


def cmd_email_daily(args):
    """把指定日期的话题产物各自打包 zip，一封日报邮件发送(正文=当天内容总结)。"""
    from . import mailer
    res = mailer.send_report(day=args.date, recipients=args.to, dry_run=args.dry_run)
    if not res.get("sent"):
        print(f"[email-daily] 未发送：{res.get('reason') or res.get('dry_run') and 'dry-run 预演'}")
        for z in res.get("zips", []):
            print(f"  - {z}")
        if res.get("total_bytes"):
            print(f"  附件合计 {res['total_bytes']/1048576:.1f} MB")
        if res.get("body"):
            print("--- 正文预览 ---")
            print(res["body"])
        return
    print(f"[email-daily] 已发送 -> {', '.join(res['to'])}，"
          f"{len(res['zips'])} 个附件，合计 {res['total_bytes']/1048576:.1f} MB：")
    for z in res["zips"]:
        print(f"  - {os.path.basename(z)}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="dlmu", description="考研自媒体自动化流水线")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db").set_defaults(func=cmd_init_db)
    sub.add_parser("seed-themes").set_defaults(func=cmd_seed_themes)
    sub.add_parser("list-themes", help="列出内容主题(供抓取/创作任务参考)").set_defaults(func=cmd_list_themes)

    p_fetch = sub.add_parser("fetch", help="运行单个抓取器")
    p_fetch.add_argument("--source", required=True, choices=["yz", "rss", "web"])
    p_fetch.add_argument("--path", help="yz: CSV 路径")
    p_fetch.add_argument("--url", help="rss: feed 地址")
    p_fetch.add_argument("--pool", nargs="*", help="目标学校池")
    p_fetch.set_defaults(func=cmd_fetch)

    sub.add_parser("fetch-all", help="运行全部自主抓取器(RSS 种子 + 全网搜索)").set_defaults(func=cmd_fetch_all)

    p_ing = sub.add_parser("ingest-web", help="把 Agent 全网检索结果批量入库")
    p_ing.add_argument("--file", required=True, help="JSON: [{title,content,url,theme_key,scope}]")
    p_ing.set_defaults(func=cmd_ingest_web)

    p_create = sub.add_parser("create", help="运行创作 Agent(外部 LLM)")
    p_create.add_argument("--limit", type=int, default=3)
    p_create.add_argument("--period", help="期号(默认今天)")
    p_create.set_defaults(func=cmd_create)

    p_select = sub.add_parser("select", help="产出候选选题简报(JSON)，供创作 Agent 写文案")
    p_select.add_argument("--limit", type=int, default=30)
    p_select.add_argument("--period", help="期号(默认今天)")
    p_select.add_argument("--theme", type=int, help="仅导出某主题(Theme.id)的选题")
    p_select.add_argument("--week", action="store_true",
                          help="周计划模式：仅导出本周组主题的选题")
    p_select.add_argument("--out", help="简报输出文件(默认打印到 stdout)")
    p_select.set_defaults(func=cmd_select)

    p_plan = sub.add_parser("plan", help="查看内容周计划(本周起,4组主题按周轮换)")
    p_plan.add_argument("--weeks", type=int, default=4, help="展示未来几周(默认4)")
    p_plan.add_argument("--out", help="写入 markdown 文件(如 outputs/weekly_plan.md)")
    p_plan.set_defaults(func=cmd_plan)

    p_mail = sub.add_parser("email-daily", help="当天话题各自打包 zip，日报邮件发送(正文=内容总结)")
    p_mail.add_argument("--date", help="日期 YYYY-MM-DD(默认今天)")
    p_mail.add_argument("--to", action="append", help="收件人(可多次；默认取 MAIL_TO)")
    p_mail.add_argument("--dry-run", action="store_true", help="只打包不发信，打印预览")
    p_mail.set_defaults(func=cmd_email_daily)

    p_save = sub.add_parser("save-draft", help="按 Agent 写好的文案 JSON 落草稿+渲染卡片")
    p_save.add_argument("--file", required=True, help="JSON: [{topic_id,title,body,tags[]}]")
    p_save.set_defaults(func=cmd_save_draft)

    p_list = sub.add_parser("list-drafts")
    p_list.add_argument("--status")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.set_defaults(func=cmd_list_drafts)

    p_verify = sub.add_parser("verify", help="对已有草稿做事实性复核，报告写入 cards/<主题名>/")
    p_verify.add_argument("--topic", required=True, help="Topic id 或 主题名/key（如 院校专业解读）")
    p_verify.set_defaults(func=cmd_verify)

    sub.add_parser("publish").set_defaults(func=cmd_publish)

    p_export = sub.add_parser("export", help="为已有草稿重新生成发布文案.md(标题/正文/话题标签/配图顺序)")
    p_export.add_argument("--topic", help="Topic id 或 主题名；缺省导出全部草稿")
    p_export.add_argument("--status", help="按草稿状态过滤(如 approved)")
    p_export.add_argument("--limit", type=int, default=50)
    p_export.set_defaults(func=cmd_export)

    p_clone = sub.add_parser("clone-voice", help="用录音做 ElevenLabs 即时克隆音色(需 ELEVENLABS_API_KEY)")
    p_clone.add_argument("--name", required=True, help="音色名，如 学姐")
    p_clone.add_argument("--file", action="append", required=True,
                         help="干净录音文件(mp3/m4a/wav)，可多次传入；建议 1-5 分钟女声无背景音")
    p_clone.add_argument("--save", action="store_true", help="把 voice_id 写入 .env 并启用 elevenlabs")
    p_clone.set_defaults(func=cmd_clone_voice)

    p_narr = sub.add_parser("narrate", help="为已有草稿重新生成语音解说(用当前音色)，不重渲图片")
    p_narr.add_argument("--topic", help="Topic id 或 主题名；缺省全部草稿")
    p_narr.add_argument("--status", help="按草稿状态过滤")
    p_narr.add_argument("--limit", type=int, default=50)
    p_narr.set_defaults(func=cmd_narrate)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
