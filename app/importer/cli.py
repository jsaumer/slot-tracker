"""``slot-tracker-import`` console entry point.

Production invokes this via ``docker exec … slot-tracker-import /import/Slots.ods``.
Idempotent: safe to re-run against a populated database. Never writes to the
source workbook (mounted read-only in production).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.db import SessionLocal
from app.importer.loader import load
from app.importer.reader import read_workbook


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="slot-tracker-import",
        description="Import Slots.ods into the slot-tracker database (idempotent).",
    )
    parser.add_argument("workbook", help="path to Slots.ods")
    args = parser.parse_args(argv)

    path = Path(args.workbook)
    if not path.is_file():
        print(f"error: workbook not found: {path}", file=sys.stderr)
        return 2

    result = read_workbook(str(path))
    with SessionLocal() as session:
        summary = load(session, result.hunts, result.bonuses)
        summary.warnings.extend(result.warnings)
        session.commit()

    print(summary.render())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
