"""Multiplier distribution bands, shared by the dashboard and the log filter.

Half-open ranges ``lo <= x < hi`` (hi=None is unbounded), so every multiplier
falls in exactly one band.
"""

from __future__ import annotations

from decimal import Decimal

# (key, label, lo, hi)
BANDS: list[tuple[str, str, Decimal, Decimal | None]] = [
    ("u10", "< 10x", Decimal(0), Decimal(10)),
    ("10_50", "10–50x", Decimal(10), Decimal(50)),
    ("50_100", "50–100x", Decimal(50), Decimal(100)),
    ("100_500", "100–500x", Decimal(100), Decimal(500)),
    ("500_1000", "500–1000x", Decimal(500), Decimal(1000)),
    ("o1000", "1000x+", Decimal(1000), None),
]

_BY_KEY = {key: (lo, hi) for key, _label, lo, hi in BANDS}
LABELS = {key: label for key, label, _lo, _hi in BANDS}


def band_bounds(key: str) -> tuple[Decimal, Decimal | None] | None:
    return _BY_KEY.get(key)


def classify(multiplier: Decimal) -> str:
    for key, _label, lo, hi in BANDS:
        if multiplier >= lo and (hi is None or multiplier < hi):
            return key
    return BANDS[-1][0]
