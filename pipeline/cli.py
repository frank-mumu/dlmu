"""命令行入口：init-db / fetch / create / list-drafts / publish。"""
import argparse

from .config import settings
from .creator import run as create_run
from .fetchers import get_fetcher
from .storage import init_db, repo, session_scope


def cmd_init_db(_args):
    init_db()
    print(f"[init-db] 已建表 -> {settings.database_url}")


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


def cmd_create(args):
    print(f"[create] {create_run(limit=args.limit, period=args.period)}")


def cmd_select(args):
    import json
    from .creator import runner
    with session_scope() as session:
        brief = runner.topics_brief(session, limit=args.limit, period=args.period)
    text = json.dumps(brief, ensure_ascii=False, indent=2)
    if args.out:
        import os
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"[select] {len(brief)} 个选题已写入 {args.out}")
    else:
        print(text)


def cmd_save_draft(args):
    import json
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


def main(argv=None):
    parser = argparse.ArgumentParser(prog="dlmu", description="考研自媒体自动化流水线")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db").set_defaults(func=cmd_init_db)

    p_fetch = sub.add_parser("fetch", help="运行抓取器")
    p_fetch.add_argument("--source", required=True, choices=["yz", "rss"])
    p_fetch.add_argument("--path", help="yz: CSV 路径")
    p_fetch.add_argument("--url", help="rss: feed 地址")
    p_fetch.add_argument("--pool", nargs="*", help="目标学校池")
    p_fetch.set_defaults(func=cmd_fetch)

    p_create = sub.add_parser("create", help="运行创作 Agent(外部 LLM)")
    p_create.add_argument("--limit", type=int, default=3)
    p_create.add_argument("--period", help="期号(默认今天)，用于标题去重")
    p_create.set_defaults(func=cmd_create)

    p_select = sub.add_parser("select", help="产出候选选题简报(JSON)，供创作 Agent 写文案")
    p_select.add_argument("--limit", type=int, default=5)
    p_select.add_argument("--period", help="期号(默认今天)")
    p_select.add_argument("--out", help="简报输出文件(默认打印到 stdout)")
    p_select.set_defaults(func=cmd_select)

    p_save = sub.add_parser("save-draft", help="按 Agent 写好的文案 JSON 落草稿+渲染卡片")
    p_save.add_argument("--file", required=True, help="JSON: [{topic_id,title,body,tags[]}]")
    p_save.set_defaults(func=cmd_save_draft)

    p_list = sub.add_parser("list-drafts")
    p_list.add_argument("--status")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.set_defaults(func=cmd_list_drafts)

    sub.add_parser("publish").set_defaults(func=cmd_publish)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
