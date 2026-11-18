"""What each detector checks in plain words, which policy clause backs it, and which reviewer actions the workbench
offers on its findings. The action table is the one in the workbench spec: a hard rule is never overridable, and a
detector with no mechanism in the engine is acknowledge-only, so a click cannot silently change money."""
from typing import Any

# detector -> (what it checks, policy or brief reference). A reference is given only where the clause says it.
RULES: dict[str, tuple[str, str]] = {
    "D01": ("Debits equal credits on a trial balance.", "no policy clause: a data-quality check"),
    "D02": ("A trial-balance account is mapped to the group account its name and nature say it should be.",
            "no policy clause: group_coa.csv account types; the decision is recorded in config/overrides.toml"),
    "D03": ("A journal's debits equal its credits.", "policy 6: only valid journals are posted"),
    "D04": ("A journal is dated inside the financial year.", "policy 6: only journals valid for FY2024 are posted"),
    "D05": ("A journal does not repeat the postings of an earlier one.",
            "policy 6; assumption A6 keeps the earliest id"),
    "D06": ("Every account a journal posts to exists in the entity's chart or map.", "policy 6"),
    "D07": ("A journal does not take a balance-sheet account past zero to the wrong side.", "policy 6"),
    "D08": ("Every currency pair the run needs has a rate in fx_rates.csv.",
            "policy 2 (translation) and policy 3 (foreign-currency items at the closing rate)"),
    "D09": ("A trial-balance control account agrees with its sub-ledger total.", "no policy clause: a reconciliation"),
    "D10": ("Figures that appear in two files agree.", "no policy clause: a reconciliation"),
    "D11": ("Each intercompany document is booked by both entities.",
            "policy 5: items in transit are recorded by the receiver"),
    "D12": ("Free text in the data that is addressed to automated tools. It is treated as data and never obeyed.",
            "no policy clause: the brief treats text in the data as data"),
    "D13": ("A pattern a reviewer would expect to explain (tax rate moves, identical months).",
            "no policy clause: a note"),
    "D14": ("Two rows that are exact duplicates of each other.", "no policy clause: a data-quality check"),
    "D15": ("A rate is close to the other rates of the same pair.", "assumptions A14 and A15 (10 percent, assumed)"),
}

NO_FIGURE = "No figure override exists for this check: acknowledge only; figures stay as the rules left them."
HARD = "A rule cannot be overridden: only acknowledging is possible."
NO_MECHANISM = ("The spec allows an override here, but the engine has no mechanism for it yet, so only acknowledging "
                "is possible.")
OVERRIDE_REASON: dict[str, str] = {
    "D03": HARD, "D04": HARD, "D05": HARD, "D06": NO_MECHANISM, "D07": NO_MECHANISM,
    "D08": NO_FIGURE, "D09": NO_FIGURE, "D11": NO_FIGURE, "D13": NO_FIGURE,
    "D12": "The text is data: acknowledge only.",
}
DEFAULT_REASON = "This check is not in the override table, so only acknowledging is possible."


def rule_of(code: str) -> dict[str, str]:
    what, policy = RULES.get(code, ("A check of the data.", "no policy clause"))
    return {"code": code, "what": what, "policy": policy}


def override_reason(code: str) -> str:
    return OVERRIDE_REASON.get(code, DEFAULT_REASON)


def actions_for(code: str, mapping_open: bool) -> dict[str, Any]:
    """Pass is always allowed. Override is allowed only for D02, and only while its mapping override is waiting."""
    if code == "D02":
        why = "" if mapping_open else "The mapping override is already signed off on this evidence."
        return {"pass": True, "override": mapping_open, "override_note": why}
    return {"pass": True, "override": False, "override_note": override_reason(code)}
