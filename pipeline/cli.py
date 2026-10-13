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
    with session_scope() as session:
        brief = runner.topics_brief(session, limit=args.limit,
                                     period=args.period, theme_id=args.theme)
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


def cmd_verify(args):
    from .creator import verifier
    with session_scope() as session:
        topic = session.get(Topic, args.topic)
        if topic is None:
            print(f"[verify] topic {args.topic} 不存在")
            return
        draft = repo.latest_draft(session, args.topic)
        if draft is None:
            print(f"[verify] topic {args.topic} 尚无草稿，无法复核")
            return
        content = {"title": draft.title, "subtitle": "", "pages": draft.pages or [],
                   "closing": "", "tags": draft.tags or []}
        out_dir = os.path.join(settings.output_dir, "cards", f"topic{args.topic}")
        if draft.assets:
            out_dir = os.path.dirname(draft.assets[0])
        report = verifier.verify_and_write(session, topic, content, out_dir)
        print(f"[verify] topic{args.topic} 结论={report['verdict']} "
              f"问题={report['counts']['total']}（高{report['counts']['high']}/中{report['counts']['mid']}）")
        print(f"          报告 -> {out_dir}/review.json + review.md")


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
    p_select.add_argument("--out", help="简报输出文件(默认打印到 stdout)")
    p_select.set_defaults(func=cmd_select)

    p_save = sub.add_parser("save-draft", help="按 Agent 写好的文案 JSON 落草稿+渲染卡片")
    p_save.add_argument("--file", required=True, help="JSON: [{topic_id,title,body,tags[]}]")
    p_save.set_defaults(func=cmd_save_draft)

    p_list = sub.add_parser("list-drafts")
    p_list.add_argument("--status")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.set_defaults(func=cmd_list_drafts)

    p_verify = sub.add_parser("verify", help="对已有草稿做事实性复核，报告写入 cards/topicN/")
    p_verify.add_argument("--topic", type=int, required=True, help="Topic id")
    p_verify.set_defaults(func=cmd_verify)

    sub.add_parser("publish").set_defaults(func=cmd_publish)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
