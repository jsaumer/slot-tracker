"""Canonical game-name alias map, transcribed verbatim from docs/build-brief.md.

38 spellings collapse into canonical names. Sequels stay distinct. Keys are the
raw spellings as they appear in the workbook; both keys and lookup inputs are run
through ``normalize_name`` (trim + whitespace collapse) before matching, so the
double-spaced entries below resolve correctly.
"""

from __future__ import annotations

# raw spelling -> canonical name
ALIAS_MAP: dict[str, str] = {
    ":egacy of Dead": "Legacy of Dead",
    "Boodthirst": "Bloodthirst",
    "Choas Crew": "Chaos Crew",
    "Chaos Crew II": "Chaos Crew 2",
    "Hanf of Anubus": "Hand of Anubus",
    "Hand of  Anubus": "Hand of Anubus",
    "Hand of Anubis": "Hand of Anubus",
    "Frutz": "Fruitz",
    "Fruit Dual": "Fruit Duel",
    "Myster Motel": "Mystery Motel",
    "True Grit Recepmtion": "True Grit Redemption",
    "San Quinin Death Row": "San Quentin Death Row",
    "San Quintin Manhunt": "San Quentin Manhunt",
    "Sugar RUsh": "Sugar Rush",
    "Money train 2": "Money Train 2",
    "Stack'Em": "Stack'em",
    "Rip City": "RIP City",
    "Frkn Bananas": "FRKN Bananas",
    "Le Pharoh": "Le Pharaoh",
    "Denscho": "Densho",
    "Warrior's Way": "Warrior Ways",
    "Outlaws Inc": "Outlaws Inc.",
    "Outlaw Inc.": "Outlaws Inc.",
    "xWays Hoarder II": "xWays Hoarder 2",
    "Pray For Six": "Pray for Six",
    "Hop'n'Pop": "Hop 'n' Pop",
    "Cursed Sea": "Cursed Seas",
    "Drac Stacks": "Drac's Stacks",
    "Rich Wilde and the Book of the Dead": "Rich Wilde and the Book of Dead",
    "Rich Wilde Tomb of Madness": "Rich Wilde and the Tome of Madness",
    "Rich Wilde's Tome of Madness": "Rich Wilde and the Tome of Madness",
    "Punk Rockers 3": "Punk Rocker 3",
    "Das xBoot": "Das Boot",
    "Das X Boot": "Das Boot",
    "Le Bandit – Miami Hustle": "Le Bandit Miami Hustle",
    "Dog House - Dog or Alive": "Dog House Dog or Alive",
    "Wanted Dead or a Wild": "Wanted Dead or Wild",
    "Wanted Dead of a Wild": "Wanted Dead or Wild",
}
