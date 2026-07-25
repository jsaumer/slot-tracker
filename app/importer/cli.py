"""Importer entry point — development use only.

No console script is installed and this module is not shipped in the container
image. Run it from a checkout against a configured ``DATABASE_URL``:

    uv run python -m app.importer.cli path/to/workbook.ods

Idempotent: safe to re-run against a populated database. Never writes to the
source workbook.
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
        prog="python -m app.importer.cli",
        description="Import an .ods workbook into the slot-tracker database (idempotent).",
    )
    parser.add_argument("workbook", help="path to the .ods workbook")
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
