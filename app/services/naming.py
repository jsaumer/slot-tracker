"""Game-name normalization used on the entry path.

Lives here rather than in ``app/importer/`` so the running application has no
dependency on importer code — the importer is development-only tooling and is not
shipped in the container image (see ``.dockerignore``).
"""

from __future__ import annotations

import re

_WHITESPACE = re.compile(r"\s+")


def normalize_name(raw: str) -> str:
    """Trim and collapse internal whitespace runs to a single space."""
    return _WHITESPACE.sub(" ", raw).strip()
