#!/usr/bin/env python3
"""
OmniSignal panel CLI — build, inspect and verify factor panel snapshots.

Usage:
    python -m src.panel.cli build --universe dev --start 2023-01-01 --publish
    python -m src.panel.cli list
    python -m src.panel.cli show --as-of 2024-06-28 --limit 10
    python -m src.panel.cli verify --all
    python -m src.panel.cli publish <snapshot_id>

Every command takes `--json` for machine-readable output, matching
`scripts/fetch_macro.py`. Exit codes are meaningful, because a rebuild is
something a scheduler will run unattended (Phase 7):

    0  success
    1  usage or runtime error
    2  snapshot already exists (rebuild refused — snapshots are immutable)
    3  integrity verification failed
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv(project_root / ".env")

from src.panel.builder import PanelBuilder  # noqa: E402
from src.panel.storage import (  # noqa: E402
    DEFAULT_ROOT,
    PanelStore,
    SnapshotExistsError,
    SnapshotNotFoundError,
)
from src.panel.universe import Universe, available  # noqa: E402

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_EXISTS = 2
EXIT_CORRUPT = 3


# ── commands ─────────────────────────────────────────────────────────────────

def cmd_build(args: argparse.Namespace) -> int:
    universe = (
        Universe.custom([s for s in args.symbols.split(",")])
        if args.symbols
        else Universe.named(args.universe)
    )
    store = PanelStore(args.root)

    builder = PanelBuilder(vectorized=not args.scalar)
    frame, manifest = builder.build(universe, args.start, args.end, step=args.step)

    try:
        written = store.write(frame, manifest)
    except SnapshotExistsError as exc:
        # Not a crash — the identical build already exists. Say so plainly
        # and exit distinctly so a scheduler can treat it as a no-op.
        _emit({"error": "snapshot_exists", "snapshot_id": manifest.snapshot_id,
               "detail": str(exc)}, args.json)
        return EXIT_EXISTS

    if args.publish:
        store.publish(written.snapshot_id)

    if args.json:
        _emit(json.loads(written.model_dump_json()), True)
    else:
        print(f"\n  snapshot     {written.snapshot_id}")
        print(f"  universe     {written.universe} ({len(written.symbols)} symbols)")
        print(f"  range        {written.start} → {written.end}  step={args.step}d")
        print(f"  rows         {written.rows:,}")
        print(f"  built        {written.symbols_built}/{len(written.symbols)}")
        if written.symbols_skipped:
            print(f"  skipped      {', '.join(written.symbols_skipped)}")
        print(f"  engine       {written.engine_version}"
              f"{'  (scalar/oracle)' if args.scalar else ''}")
        print(f"  content      {written.content_hash[:16]}…")
        print(f"  build time   {written.build_seconds:.2f}s")
        print(f"  published    {'yes' if args.publish else 'no'}\n")
    return EXIT_OK


def cmd_list(args: argparse.Namespace) -> int:
    store = PanelStore(args.root)
    snapshots = store.list_snapshots()
    current = store.current()

    if args.json:
        _emit(
            {
                "current": current,
                "snapshots": [json.loads(m.model_dump_json()) for m in snapshots],
            },
            True,
        )
        return EXIT_OK

    if not snapshots:
        print(f"\n  no snapshots under {store.root}\n")
        return EXIT_OK

    print(f"\n  {'':1} {'SNAPSHOT':18} {'UNIVERSE':10} {'RANGE':25} {'ROWS':>9}  CREATED")
    for manifest in snapshots:
        marker = "*" if manifest.snapshot_id == current else " "
        span = f"{manifest.start} → {manifest.end}"
        print(
            f"  {marker} {manifest.snapshot_id:18} {manifest.universe:10} "
            f"{span:25} {manifest.rows:>9,}  "
            f"{manifest.created_at.strftime('%Y-%m-%d %H:%M')}"
        )
    print("\n  * = published (CURRENT)\n")
    return EXIT_OK


def cmd_show(args: argparse.Namespace) -> int:
    store = PanelStore(args.root)
    manifest = store.manifest(args.snapshot_id)

    frame = (
        store.read_as_of(args.as_of, args.snapshot_id)
        if args.as_of
        else store.read(args.snapshot_id)
    )
    if args.symbol:
        frame = frame[frame["symbol"] == args.symbol.upper()]

    if args.json:
        _emit(
            {
                "manifest": json.loads(manifest.model_dump_json()),
                "rows": json.loads(frame.head(args.limit).to_json(orient="records")),
            },
            True,
        )
        return EXIT_OK

    print(f"\n  snapshot {manifest.snapshot_id}  ({manifest.rows:,} rows total)")
    if args.as_of:
        print(f"  point-in-time read: as_of <= {args.as_of} → {len(frame):,} rows visible")
    print()
    if frame.empty:
        print("  no rows match\n")
        return EXIT_OK

    with_values = frame.head(args.limit)
    print(with_values.to_string(max_cols=12, index=False))
    print()
    return EXIT_OK


def cmd_verify(args: argparse.Namespace) -> int:
    store = PanelStore(args.root)
    targets = (
        [m.snapshot_id for m in store.list_snapshots()]
        if args.all
        else [store._resolve(args.snapshot_id)]  # noqa: SLF001 — same package
    )
    if not targets:
        _emit({"error": "no snapshots to verify"}, args.json)
        return EXIT_ERROR

    results = {snapshot_id: store.verify(snapshot_id) for snapshot_id in targets}
    ok = all(results.values())

    if args.json:
        _emit({"ok": ok, "results": results}, True)
    else:
        print()
        for snapshot_id, passed in results.items():
            print(f"  {'OK  ' if passed else 'FAIL'}  {snapshot_id}")
        print()
    return EXIT_OK if ok else EXIT_CORRUPT


def cmd_publish(args: argparse.Namespace) -> int:
    store = PanelStore(args.root)
    store.publish(args.snapshot_id)
    _emit({"current": args.snapshot_id}, args.json)
    if not args.json:
        print(f"\n  CURRENT → {args.snapshot_id}\n")
    return EXIT_OK


# ── plumbing ─────────────────────────────────────────────────────────────────

def _emit(payload: object, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, default=str))
    elif isinstance(payload, dict) and "error" in payload:
        print(f"\n  error: {payload.get('detail') or payload['error']}\n", file=sys.stderr)


def _iso_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {value!r}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.panel.cli",
        description="Build, inspect and verify point-in-time factor panel snapshots.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT,
                        help=f"panel root directory (default: {DEFAULT_ROOT})")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--verbose", "-v", action="store_true", help="log build progress")
    sub = parser.add_subparsers(dest="command", required=True)

    today = date.today()

    p_build = sub.add_parser("build", help="build a new snapshot")
    p_build.add_argument("--universe", default="dev",
                         help=f"named universe: {', '.join(available())} (default: dev)")
    p_build.add_argument("--symbols", default=None,
                         help="comma-separated symbols; overrides --universe")
    p_build.add_argument("--start", type=_iso_date, default=today - timedelta(days=730),
                         help="first observation date (default: 2 years ago)")
    p_build.add_argument("--end", type=_iso_date, default=today,
                         help="last observation date (default: today)")
    p_build.add_argument("--step", type=int, default=1,
                         help="observation stride in trading days (default: 1)")
    p_build.add_argument("--publish", action="store_true",
                         help="point CURRENT at the new snapshot")
    p_build.add_argument("--scalar", action="store_true",
                         help="force the scalar engine (the oracle: ~30x slower, "
                              "correct by definition) instead of the fast path")
    p_build.set_defaults(func=cmd_build)

    p_list = sub.add_parser("list", help="list snapshots")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="print rows from a snapshot")
    p_show.add_argument("snapshot_id", nargs="?", default=None,
                        help="snapshot id (default: CURRENT)")
    p_show.add_argument("--as-of", type=_iso_date, default=None,
                        help="point-in-time read: only rows knowable by this date")
    p_show.add_argument("--symbol", default=None, help="filter to one symbol")
    p_show.add_argument("--limit", type=int, default=20, help="rows to print (default: 20)")
    p_show.set_defaults(func=cmd_show)

    p_verify = sub.add_parser("verify", help="check stored bytes against the manifest hash")
    p_verify.add_argument("snapshot_id", nargs="?", default=None,
                          help="snapshot id (default: CURRENT)")
    p_verify.add_argument("--all", action="store_true", help="verify every snapshot")
    p_verify.set_defaults(func=cmd_verify)

    p_publish = sub.add_parser("publish", help="point CURRENT at a snapshot")
    p_publish.add_argument("snapshot_id")
    p_publish.set_defaults(func=cmd_publish)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        return int(args.func(args))
    except (SnapshotNotFoundError, KeyError, ValueError) as exc:
        _emit({"error": type(exc).__name__, "detail": str(exc)}, args.json)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
