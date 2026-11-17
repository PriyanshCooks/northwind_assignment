"""Binds config/policy.toml to group_policies.md by hash (change the text without re-approval and the run blocks), and
reads the clauses with a lexicon to check that the approved config still says what the text says."""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.domain.policy import Policy
from app.utils.hashing import sha256_file


class PolicyBlocked(Exception):
    """group_policies.md no longer matches the text policy.toml was approved against."""


def check_binding(policy: Policy, data_dir: Path) -> None:
    """Policy-dependent steps cannot run on a policy nobody approved. Re-approve by updating source_sha256."""
    source = data_dir / Path(policy.meta.source).name
    actual = sha256_file(source)
    if actual != policy.meta.source_sha256:
        raise PolicyBlocked(
            f"{source.name} has changed since config/policy.toml was approved (hash {actual[:12]}, approved "
            f"{policy.meta.source_sha256[:12]}): re-read the policy and approve it again before the run continues"
        )


@dataclass(frozen=True)
class Reading:
    """One policy choice read from the text: the value (None if unreadable), its clause and the sentence."""

    field: str  # section.key as in policy.toml, for example translation.assets_liabilities
    value: str | None
    clause: int
    quote: str
    reason: str = ""
    reader: str = "LEXICON"


CLOSING = r"\b(closing|year[- ]end|balance sheet date|reporting date)\b"
# field -> (clause, regex that finds the sentence about it, {value: regex that says it})
LEXICON: dict[str, tuple[int, str, dict[str, str]]] = {
    "translation.assets_liabilities": (2, r"assets and liabilities", {"closing": CLOSING, "average": r"\baverage\b",
                                                                      "historical": r"\bhistorical\b"}),
    "translation.income_expenses": (2, r"income and expenses", {"average_for_inclusion_period": r"\baverage\b",
                                                                "closing": CLOSING, "historical": r"\bhistorical\b"}),
    "translation.equity": (2, r"^\s*equity\b", {"historical": r"\bhistorical\b", "closing": CLOSING}),
    "foreign_currency_items.monetary_items": (3, r"monetary items", {"closing": CLOSING, "average": r"\baverage\b"}),
    "business_combination.nci_measurement": (4, r"non-controlling", {
        "proportionate_share_of_net_assets": r"proportionate share", "fair_value": r"fair value"}),
    "business_combination.goodwill_translation": (4, r"goodwill", {"closing": CLOSING,
                                                                   "historical": r"\bhistorical\b"}),
    "intercompany.elimination": (5, r"eliminated", {"full": r"\b(in full|fully|entirely)\b",
                                                    "partial": r"\b(partial|partly|proportion)"}),
    "journals.posting_rule": (6, r"posted", {"valid_for_period_only": r"\b(valid for|only if)\b"}),
}


def clauses(text: str) -> dict[int, str]:
    """The numbered clauses of group_policies.md, each with its bullets."""
    parts = re.split(r"(?m)^(\d+)\.\s", text)
    return {int(parts[i]): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def _sentences(clause: str) -> list[str]:
    """Bullets stay apart, wrapped lines are joined, then each piece is split into sentences."""
    bullets = [re.sub(r"\s+", " ", b) for b in re.split(r"\n\s*- ", clause.strip())]
    return [s.strip() for b in bullets for s in re.split(r"(?<=[.])\s+(?=[A-Z])", b) if s.strip()]


def read_policy(text: str) -> list[Reading]:
    """A lexicon reader: it knows a few ways to say each choice. A clause it cannot read gives None, never a guess."""
    found = clauses(text)
    readings = []
    for field, (number, locate, options) in LEXICON.items():
        sentences = [s for s in _sentences(found.get(number, "")) if re.search(locate, s, re.IGNORECASE)]
        if not sentences:
            readings.append(Reading(field, None, number, "", f"clause {number} has no sentence about this"))
            continue
        quote = sentences[0]
        hits = [value for value, pattern in options.items() if re.search(pattern, quote, re.IGNORECASE)]
        if len(hits) == 1:
            readings.append(Reading(field, hits[0], number, quote))
        else:
            why = "no wording the lexicon knows" if not hits else f"ambiguous between {' and '.join(hits)}"
            readings.append(Reading(field, None, number, quote, why))
    return readings


def compare(readings: list[Reading], approved_values: dict[str, Any]) -> list[tuple[str, str]]:
    """Fields where the text and config/policy.toml disagree or the text could not be read: (field, what)."""
    problems = []
    for reading in readings:
        section, key = reading.field.split(".")
        approved = approved_values[section][key]
        if reading.value is None:
            problems.append((reading.field, f"unreadable ({reading.reason}); policy.toml says {approved}"))
        elif reading.value != approved:
            said = f"clause {reading.clause} reads {reading.value}"
            problems.append((reading.field, f"{said}; policy.toml says {approved}"))
    return problems
