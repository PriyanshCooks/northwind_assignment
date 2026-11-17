"""D12 instruction-like wording in free text. A second layer only: text is data and approves nothing."""
import re

from app.domain.findings import Finding, new_finding
from app.domain.quarantine import Quarantined
from app.domain.refs import SourceRef
from app.domain.runs import Context

PATTERNS = tuple(re.compile(p, re.IGNORECASE) for p in (
    r"\b(automated|ai)\b.{0,40}\b(reviewers?|assistants?|tools?|agents?)\b",
    r"\bpre-?approved\b",
    r"\bskip (the )?(debit/credit )?(balance )?check",
    r"\bdo not (list|report|flag|mention)\b",
    r"\bignore (all |any )?(previous |prior |above )?(instructions|rules|checks)",
    r"\bmark (it |this )?as (accepted|approved)\b",
))


def _texts(ctx: Context) -> list[tuple[str, SourceRef]]:
    items = [(line.local_name.text, line.ref) for lines in ctx.inputs.trial_balances.values() for line in lines]
    for index in ctx.inputs.maps.values():
        items += [(row.local_name.text, row.ref) for rows in index.values() for row in rows]
    items += [(account.name, account.ref) for account in ctx.inputs.coa.values()]
    for journal in ctx.inputs.journals:
        items.append((journal.description.text, journal.ref))
        items += [(line.memo.text, line.memo_ref or line.ref) for line in journal.lines if line.memo is not None]
    return items


def d12_instruction_wording(ctx: Context) -> list[Finding]:
    found = []
    for text, ref in _texts(ctx):
        if any(pattern.search(text) for pattern in PATTERNS):
            claim = ("free text addressed to automated tools was found and treated as data; "
                     "it was not obeyed and cannot change any decision")
            found.append(new_finding("D12", "FLAG", claim, ref.file, ref.line, "flagged", None, "text",
                                     (ref,), Quarantined(text=text)))
    return found
