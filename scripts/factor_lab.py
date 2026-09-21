"""Explicit offline Factor Lab artifact builder."""

from __future__ import annotations

import argparse

from src.services.factor_lab_service import build_artifact


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--universe", default="mega30")
    build.add_argument("--years", type=float, default=2.5)
    build.add_argument("--horizon", type=int, default=21)
    args = parser.parse_args()
    path = build_artifact(args.universe, args.years, args.horizon)
    print(f"published {path}")


if __name__ == "__main__":
    main()
