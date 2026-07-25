"""Plain data carriers passed from the reader to the loader.

Keeping these free of SQLAlchemy lets the reader be tested without a database and
the loader be tested without the workbook.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class HuntRecord:
    import_ref: str  # "hunt:N"
    label: str
    hunt_date: date | None = None
    start_balance: Decimal | None = None
    end_balance: Decimal | None = None
    end_convention: str = "after_opening"
    notes: str | None = None


@dataclass
class BonusRecord:
    import_ref: str  # "main:R" | "hunt:N:R" | "notable:R"
    game_name: str  # raw spelling; canonicalized by the loader
    # None for hunt/notable rows — those source layouts carry no per-bonus date.
    played_on: date | None
    bet: Decimal
    win: Decimal
    notes: str | None = None
    replay_url: str | None = None
    notable: bool = False
    date_suspect: bool = False
    hunt_ref: str | None = None  # link to a HuntRecord.import_ref


@dataclass
class ImportSummary:
    """Counts printed at the end of a run and checked against DEPLOY.md step 7."""

    bonuses_inserted: int = 0
    bonuses_updated: int = 0
    games_created: int = 0
    hunts_created: int = 0
    hunts_updated: int = 0
    suspects_flagged: int = 0
    notable_flagged: int = 0
    # Post-run totals in the database, for cross-checking against expected figures.
    total_bonuses: int = 0
    total_games: int = 0
    total_hunts: int = 0
    warnings: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            "import summary",
            "-------------------------------------------",
            f"  bonuses inserted : {self.bonuses_inserted}",
            f"  bonuses updated  : {self.bonuses_updated}",
            f"  games created    : {self.games_created}",
            f"  hunts created    : {self.hunts_created}",
            f"  hunts updated    : {self.hunts_updated}",
            f"  suspects flagged : {self.suspects_flagged}",
            f"  notable flagged  : {self.notable_flagged}",
            "-------------------------------------------",
            f"  total bonuses    : {self.total_bonuses}",
            f"  total games      : {self.total_games}",
            f"  total hunts      : {self.total_hunts}",
        ]
        if self.warnings:
            lines.append("-------------------------------------------")
            lines.append(f"  warnings ({len(self.warnings)}):")
            lines.extend(f"    - {w}" for w in self.warnings)
        return "\n".join(lines)
