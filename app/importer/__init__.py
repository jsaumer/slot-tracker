"""Slots.ods importer.

Split into three layers so the correctness-critical parts are testable without
the workbook or a Postgres database:

- ``normalize`` — pure string/date helpers (alias folding, URL repair, suspect
  dates).
- ``reader``    — reads Slots.ods into plain record objects (pandas + odfpy).
- ``loader``    — idempotently loads records into the database.

The console entry point is ``app.importer.cli:main`` (see pyproject scripts).
"""
