"""Grounding: each claim in a verdict is checked on its own against the packet. A claim the packet does not support is
dropped and logged; the others stand. The same exact predicates feed the rule-based fallback."""
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.agents.journal_reviewer.schema import JournalVerdict
from app.agents.mapping_reviewer.schema import MappingVerdictBase
from app.detectors.text_scan import PATTERNS

MIN_SHARED = 2  # a name matches another account only if they share two words: one word ("costs") is not enough


@dataclass(frozen=True)
class Grounded:
    verified: tuple[str, ...]
    dropped: tuple[tuple[str, str], ...]
    unverified: tuple[str, ...] = ()

    @property
    def risk(self) -> bool:
        """Only verified claims count."""
        return bool(self.verified)


def journal_facts(packet: dict[str, Any]) -> dict[str, bool]:
    """What the packet proves, category by category. Wording of free text cannot be proved, so it is not here."""
    start, end = packet["period"]
    lines = packet["lines"]
    flips = False
    for line in lines:
        if line.get("statement") != "BS":
            continue
        before, after = Decimal(line["balance_before"]), Decimal(line["balance_after"])
        flips |= (after > 0 >= before) if line["normal_balance"] == "Credit" else (after < 0 <= before)
    return {
        "unbalanced": packet["total_debit"] != packet["total_credit"],
        "outside_period": not start <= packet["date"] <= end,
        "account_not_in_chart": any(not line["in_entity_chart"] for line in lines),
        "duplicate_of_another": bool(packet["same_lines_as"]),
        "reversal_of_another": bool(packet["mirror_image_of"]),
        "exceeds_balance": flips,
    }


def _texts(packet: dict[str, Any]) -> list[str]:
    quoted = [packet["description"], *(line["memo"] for line in packet["lines"] if line["memo"])]
    return [json.loads(q) for q in quoted]


def ground_journal(verdict: JournalVerdict, packet: dict[str, Any]) -> Grounded:
    facts = journal_facts(packet)
    verified: list[str] = []
    dropped: list[tuple[str, str]] = []
    unverified: list[str] = []
    for flag in verdict.flags:
        if flag == "text_contains_instruction":
            lexicon = any(p.search(t) for t in _texts(packet) for p in PATTERNS)
            (verified if lexicon else unverified).append(flag)
        elif facts[flag]:
            verified.append(flag)
        else:
            dropped.append((flag, f"the packet does not support {flag}"))
    return Grounded(tuple(verified), tuple(dropped), tuple(unverified))


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 3}


def mapping_facts(packet: dict[str, Any], coa: dict[str, dict[str, str]]) -> tuple[dict[str, bool], str]:
    """Exact sign test, and the best other group account by shared words with the local name (or "none")."""
    mapped = packet["mapped_to"]
    local = _words(json.loads(packet["local_name"]))
    own = len(local & _words(mapped["name"]))
    best, best_score = "none", max(own, MIN_SHARED - 1)
    for code, account in sorted(coa.items()):
        score = len(local & _words(account["name"]))
        if code != mapped["code"] and score > best_score:
            best, best_score = code, score
    side, normal = packet["balance_side"], mapped["normal_balance"]
    return {
        "sign_unusual": Decimal(packet["balance"]) != 0 and side != normal.lower(),
        "name_mismatch": best != "none",
        "wrong_statement_type": best != "none" and coa[best]["statement"] != mapped["statement"],
    }, best


def _mapping_claim_holds(flag: str, proposed: str, packet: dict[str, Any], coa: dict[str, dict[str, str]]) -> bool:
    mapped = packet["mapped_to"]
    if flag == "sign_unusual":
        return mapping_facts(packet, coa)[0][flag]
    if proposed == "none" or proposed not in coa or proposed == mapped["code"]:
        return False
    if flag == "wrong_statement_type":
        return coa[proposed]["statement"] != mapped["statement"]
    local = _words(json.loads(packet["local_name"]))
    shared = len(local & _words(coa[proposed]["name"]))
    return shared >= MIN_SHARED and shared > len(local & _words(mapped["name"]))


def ground_mapping(verdict: MappingVerdictBase, packet: dict[str, Any], coa: dict[str, dict[str, str]]) -> Grounded:
    proposed = getattr(verdict, "better_group_code", "none")
    verified: list[str] = []
    dropped: list[tuple[str, str]] = []
    for flag in verdict.flags:
        if _mapping_claim_holds(flag, proposed, packet, coa):
            verified.append(flag)
        else:
            dropped.append((flag, f"the packet does not support {flag}"))
    return Grounded(tuple(verified), tuple(dropped))
