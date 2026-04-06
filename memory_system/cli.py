from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from memory_system.indexer import MemoryIndexer
    from memory_system.searcher import MemorySearcher
    from memory_system.workflow import build_context_pack, format_pack
else:
    from .indexer import MemoryIndexer
    from .searcher import MemorySearcher
    from .workflow import build_context_pack, format_pack

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local memory system index/search CLI")
    parser.add_argument(
        "--root",
        default=None,
        help="Root directory to index/search (default: use configured DEFAULT_SOURCE_DIRS from config.py)",
    )
    parser.add_argument("--db", default=None, help="SQLite index path (default: <root>/memory_index.sqlite3)")

    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build", help="Full rebuild index")
    build_parser.add_argument("--json", action="store_true", help="Print JSON result")

    update_parser = subparsers.add_parser("update", help="Incremental update index")
    update_parser.add_argument("--json", action="store_true", help="Print JSON result")

    search_parser = subparsers.add_parser("search", help="Search indexed content")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("-n", "--limit", type=int, default=10, help="Max results")
    search_parser.add_argument("--json", action="store_true", help="Print JSON result")
    search_parser.add_argument("--no-semantic", action="store_true", help="Disable semantic search")

    pack_parser = subparsers.add_parser("pack", help="Build a minimal context pack from search results")
    pack_parser.add_argument("query", help="Query to build a context pack for")
    pack_parser.add_argument("--json", action="store_true", help="Print JSON result")
    pack_parser.add_argument("--no-semantic", action="store_true", help="Disable semantic search")
    pack_parser.add_argument("-n", "--limit", type=int, default=8, help="Max search hits before packing")
    pack_parser.add_argument("--max-items", type=int, default=3, help="How many hits to keep in the final pack")

    return parser


def _print_human_results(results: list[dict]) -> None:
    if not results:
        print("No results.")
        return
    for index, item in enumerate(results, 1):
        print(f"[{index}] {item['path']}")
        if item.get("title"):
            print(f"  title : {item['title']}")
        print(f"  score : {item['score']:.4f} ({item['source']})")
        print(f"  chunk : {item['chunk_id']}")
        print(f"  match : {item['snippet'] or item['content'][:160]}")
        print()


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    root = Path(args.root) if args.root is not None else None
    db_path = Path(args.db) if args.db else None

    if args.command == "build":
        result = MemoryIndexer(root=root, db_path=db_path).build()
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"Build complete: {result['files_indexed']} files, {result['chunks_indexed']} chunks")
            if result.get("status") == "rebuilt_from_incompatible_schema":
                print(result.get("note", ""))
        return 0

    if args.command == "update":
        result = MemoryIndexer(root=root, db_path=db_path).update()
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(
                "Update complete: "
                f"{result['files_indexed']} files updated, "
                f"{result['chunks_indexed']} chunks indexed, "
                f"{result['files_removed']} files removed"
            )
            if result.get("note"):
                print(result["note"])
        return 0

    if args.command == "search":
        searcher = MemorySearcher(root=root, db_path=db_path)
        results = searcher.search_json(
            query=args.query,
            limit=args.limit,
            use_semantic=not args.no_semantic,
        )
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            _print_human_results(results)
        return 0

    if args.command == "pack":
        searcher = MemorySearcher(root=root, db_path=db_path)
        results = searcher.search_json(
            query=args.query,
            limit=args.limit,
            use_semantic=not args.no_semantic,
        )
        pack = build_context_pack(args.query, results, max_items=max(1, args.max_items))
        if args.json:
            print(json.dumps(pack, ensure_ascii=False, indent=2))
        else:
            print(format_pack(pack))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
