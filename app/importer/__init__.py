"""Development-only `.ods` importer.

**Not part of the running application.** This package ships no console entry point
and is excluded from the container image (see ``.dockerignore``); its pandas/odfpy
dependencies are only needed to run it locally. Nothing under ``app/`` imports it —
the shared name-normalization helper lives in ``app/services/naming.py``.

Kept in the repository because it encodes how the original data set was interpreted,
and because its tests cover alias handling and idempotency. To run it, invoke
``app.importer.cli:main`` directly from a development checkout.

Split into three layers so the correctness-critical parts are testable without the
workbook or a PostgreSQL database:

- ``normalize`` — pure string/date helpers (alias folding, URL repair, suspect dates).
- ``reader``    — reads a workbook into plain record objects (pandas + odfpy).
- ``loader``    — idempotently loads records into the database.
"""
