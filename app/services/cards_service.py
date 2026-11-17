"""Issue cards: each finding in plain English, from its own data. Nothing is invented: the headline reuses the finding's
claim with its numbers tidied, the rules text comes from its action and the journal's disposition, and the AI line comes
from the recorded review of the same journal or account. A finding with no matching unit reads 'not reviewed'."""
import re
from typing import Any

from app.services.overrides_service import OverrideState

AMOUNT = re.compile(r"(?<![\w.])(\d{4,})\.(\d{2})\b")
ENTITY_CODE = re.compile(r"\b(UK|US|IN) ([A-Z0-9-]{3,})\b")
JOURNAL = re.compile(r"\bJE-\d+\b")
RULES = {
    "blocked": "Blocked by the rules: the item is not used until a person decides.",
    "assumed": "The rules applied a stated assumption and carried on.",
    "flagged": "Flagged by the rules: the figures stay as supplied and the issue is reported.",
    "noted": "Noted by the rules: no figure changed.",
}
DISPOSITION = {"POST": "posted", "REJECT": "rejected and not posted", "HOLD": "held for a person to decide"}
ORDER = {"BLOCK": 0, "FLAG": 1, "NOTE": 2}
FIGURE_NAMES = {
    "group_revenue": "Group revenue", "group_profit": "Group profit", "profit_owners": "Profit attributable to owners",
    "profit_nci": "Profit attributable to non-controlling interest", "nci_closing": "Closing non-controlling interest",
    "goodwill_closing": "Closing goodwill", "translation_reserve_movement": "Translation reserve movement",
    "total_assets": "Total assets", "total_equity": "Total equity",
    "intercompany_difference": "Intercompany difference",
    "sgd_bank_gbp": "The Singapore dollar bank balance in GBP", "journals": "The journal counts",
}
FIGURE_CLAIM = re.compile(r"^(\w+) is (provisional|null)\b")


def plain(text: str) -> str:
    """1985000.00 -> 1,985,000 ; 23010.55 -> 23,010.55. Dates, rates and account codes have no cents part and stay."""
    def one(m: re.Match[str]) -> str:
        whole = f"{int(m[1]):,}"
        return whole if m[2] == "00" else f"{whole}.{m[2]}"
    return AMOUNT.sub(one, text)


def _subject(item: dict[str, Any]) -> str | None:
    found = JOURNAL.search(item["claim"])
    return item.get("subject") or (found.group(0) if found else None)


def _unit_for(item: dict[str, Any], units: list[dict[str, Any]]) -> dict[str, Any] | None:
    subject = _subject(item)
    if subject:
        return next((u for u in units if u["unit"] == subject), None)
    match = ENTITY_CODE.search(item["claim"])
    return next((u for u in units if match and u["unit"].startswith(f"{match[1]}:{match[2]}:")), None)


def _ai(unit: dict[str, Any] | None, about_text: bool = False) -> dict[str, str]:
    if unit is None:
        return {"state": "not_reviewed",
                "text": "Not reviewed by the AI: it looks only at trial-balance mappings and journals."}
    if not unit["recorded"]:
        return {"state": "not_reviewed", "text": "No recorded AI answer here; the rule-based proposer was used."}
    if about_text:  # free text is not a fact the data can prove, so the AI's other claims say nothing about it
        return {"state": "no_claim", "text": f"The AI reviewed {unit['unit']} and did not raise this text."}
    if unit["missed"]:
        said = ", ".join(unit["missed"])
        return {"state": "disagrees", "text": f"The recorded AI answer did not report {said}, which the rules found."}
    if unit["verified"]:
        said = ", ".join(unit["verified"])
        return {"state": "agrees", "text": f"The recorded AI answer agrees and the supplied data backs it: {said}."}
    return {"state": "no_claim", "text": "The AI reviewed this item and did not flag it."}


def _figure(item: dict[str, Any]) -> str | None:
    found = FIGURE_CLAIM.match(item["claim"]) if item["code"] == "FIG" else None
    return found[1] if found and found[1] in FIGURE_NAMES else None


def _memo_note(memo: dict[str, Any]) -> str:
    """Say what the memo asks only when its own words say so; otherwise just that it is addressed to reviewers."""
    asks = re.search(r"skip.{0,40}check", memo["text"], re.IGNORECASE)
    return ("; its memo on line %d asks reviewers to skip the check and is treated as data" if asks
            else "; its memo on line %d is addressed to automated reviewers and is treated as data") % memo["line"]


def _headline(item: dict[str, Any], memos: dict[str, dict[str, Any]]) -> str:
    text = plain(item["claim"]).replace(" is unbalanced", " does not balance")
    figure = FIGURE_CLAIM.match(text)
    if item["code"] == "FIG" and figure and figure[1] in FIGURE_NAMES:
        verb = "is provisional" if figure[2] == "provisional" else "cannot be determined"
        text = f"{FIGURE_NAMES[figure[1]]} {verb}" + text[figure.end():]
    if item["code"] == "D12":
        owner = next((j for j, m in memos.items() if m["line"] == item["line"]), None)
        where = f"{item['file']} line {item['line']}" + (f" ({owner})" if owner else "")
        text = f"Text addressed to automated tools was found in {where}; it is treated as data and not obeyed"
    elif item["code"] == "D03" and _subject(item) in memos:
        text += _memo_note(memos[str(_subject(item))])
    return text[0].upper() + text[1:]


def build_cards(items: list[dict[str, Any]], units: list[dict[str, Any]], dispositions: list[dict[str, Any]],
                open_items: list[str], memos: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    decided = {d["journal_id"]: d for d in dispositions}
    cards = []
    for item in items:
        memo_text = item["code"] == "D12"
        owner = next((j for j, m in memos.items() if m["line"] == item.get("line")), None) if memo_text else None
        item = item | {"subject": owner} if owner else item
        unit, subject = _unit_for(item, units), _subject(item)
        rules = RULES[item["action"]]
        if subject in decided:
            rules += f" {subject} is {DISPOSITION[decided[subject]['status']]}."
        needs = item.get("key") in open_items
        cards.append({
            "key": item.get("key"), "figure": _figure(item), "code": item["code"], "severity": item["severity"],
            "headline": _headline(item, memos),
            "evidence": {"file": item["file"], "line": item.get("line")}, "rules": rules,
            "ai": _ai(unit, memo_text),
            "quote": next((m["text"] for m in memos.values() if item["code"] == "D12" and m["line"] == item["line"]),
                          None),
            "dropped": unit["dropped"] if unit else [], "needs_decision": needs,
            "actions": ["approve", "reject"] if needs else [],
        })
    return sorted(cards, key=lambda c: (not c["needs_decision"], ORDER[c["severity"]]))


def waiting_cards(states: list[OverrideState], open_items: list[str]) -> list[dict[str, Any]]:
    """One card per item a person must decide: its reason and what each choice does to the run. Approving signs the
    decision off on today's evidence; rejecting drops it, and the override's effect_if_reversed says what follows."""
    stale = "The evidence changed since this was decided, so the decision no longer applies. "
    cards = []
    for s in states:
        o = s.override
        if o.target not in open_items:
            continue
        place = o.target.split(":", 1)[1].replace(":", " ")
        cards.append({
            "key": o.target, "state": s.state, "headline": f"{place}: {o.decision} to {o.to}",
            "reason": (stale if s.state == "stale" else "") + o.reason,
            "approve_effect": f"The {o.decision} to {o.to} applies and is signed off in your name on today's evidence.",
            "reject_effect": f"The {o.decision} is dropped. {o.effect_if_reversed}",
        })
    return cards
