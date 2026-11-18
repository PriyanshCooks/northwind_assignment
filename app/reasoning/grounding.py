"""Citation grounding: a claim stands only if its citation exists and every number or text it quotes is in the evidence
the model was given. Claims that stand are then split in two tiers. Verified: code can confirm the fact itself.
Suspicion: the model thinks something is off and no rule proves it; it is shown, never counted, never gates."""
import re
from dataclasses import dataclass
from typing import Literal

from app.reasoning.contradiction import contradicted_line
from app.reasoning.evidence import Evidence
from app.reasoning.schema import LineClaim
from app.reasoning.text_checks import WORD, invalid_date

Tier = Literal["verified", "suspicion"]
NUMBER = re.compile(r"\d[\d,.]*\d|\d")


@dataclass(frozen=True)
class Grounded:
    cite: str
    flag: str
    reason: str
    tier: Tier


@dataclass(frozen=True)
class Dropped:
    cite: str
    flag: str
    why: str


def numbers_outside(text: str, evidence_text: str) -> list[str]:
    """Numbers written in `text` that the evidence does not contain (compared without thousands separators)."""
    plain = evidence_text.replace(",", "")
    return [n for n in NUMBER.findall(text) if n.replace(",", "") not in plain]


def confirms(flag: str, cite: str, line: str, evidence: Evidence) -> bool:
    """Can code prove this flag on this line? Only three can; the rest stay suspicion."""
    if flag == "value_not_plausible":
        return invalid_date(line, evidence.last_year)
    if flag == "no_valid_name":
        return WORD.search(line) is None
    return cite in evidence.confirmed.get(flag, frozenset())


def _cited_line(cite: str, file: str, evidence: Evidence) -> str | None:
    name, _, number = cite.rpartition(":")
    if name != file or not number.isdigit():
        return None
    lines = evidence.lines(file)
    return lines[int(number) - 1] if 1 <= int(number) <= len(lines) else None


def ground_line_claims(
    claims: list[LineClaim], file: str, shown: str, evidence: Evidence,
) -> tuple[list[Grounded], list[Dropped]]:
    """`shown` is exactly the text the model was given for this chunk."""
    kept: list[Grounded] = []
    dropped: list[Dropped] = []
    seen: set[tuple[str, str]] = set()
    for claim in claims:
        line = _cited_line(claim.cite, file, evidence)
        outside = [q for q in claim.quoted if q not in shown] + numbers_outside(claim.reason, shown)
        if line is None:
            dropped.append(Dropped(claim.cite, claim.flag, "the cited line does not exist in this file"))
        elif outside:
            dropped.append(Dropped(claim.cite, claim.flag, f"not in the evidence shown: {', '.join(outside)}"))
        elif (why := contradicted_line(claim.flag, claim.cite, line, claim.quoted, evidence)) is not None:
            dropped.append(Dropped(claim.cite, claim.flag, why))
        elif (claim.cite, claim.flag) not in seen:
            seen.add((claim.cite, claim.flag))
            tier: Tier = "verified" if confirms(claim.flag, claim.cite, line, evidence) else "suspicion"
            kept.append(Grounded(claim.cite, claim.flag, claim.reason, tier))
    return kept, dropped
