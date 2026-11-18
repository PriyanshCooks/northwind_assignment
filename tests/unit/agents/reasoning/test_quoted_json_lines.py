"""A claim that quotes a line of a JSON file exactly must not be dropped for the quote marks inside it."""
from pathlib import Path

from app.agents.reasoning.evidence import Evidence
from app.agents.reasoning.grounding import ground_line_claims
from app.agents.reasoning.reader import chunk_packets
from app.agents.reasoning.schema import LineClaim
from app.utils.paths import DEFAULT_DATA_DIR


def evidence(data_dir: Path) -> Evidence:
    return Evidence(data_dir=data_dir, files=frozenset({"adjustments.json"}))


def test_an_exact_quote_of_a_json_line_is_found_in_what_the_model_was_shown() -> None:
    ev = evidence(DEFAULT_DATA_DIR)
    _, shown = chunk_packets(ev, "adjustments.json")[0]
    line = ev.lines("adjustments.json")[11]
    assert '"' in line
    claim = LineClaim(cite="adjustments.json:12", flag="value_not_plausible", reason="odd", quoted=[line.strip()])
    kept, dropped = ground_line_claims([claim], "adjustments.json", shown, ev)
    assert len(kept) == 1 and dropped == []


def test_a_quote_that_is_not_in_the_chunk_is_still_dropped() -> None:
    ev = evidence(DEFAULT_DATA_DIR)
    _, shown = chunk_packets(ev, "adjustments.json")[0]
    claim = LineClaim(cite="adjustments.json:12", flag="value_not_plausible", reason="odd", quoted=['"amount": "99"'])
    kept, dropped = ground_line_claims([claim], "adjustments.json", shown, ev)
    assert kept == [] and "not in the evidence shown" in dropped[0].why
