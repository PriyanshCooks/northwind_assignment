"""The two-boys example from the design: a tiny engine, the three checkpoints and what each one adds."""
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.domain.calculations import CalcRecord
from app.llm.ledger import Ledger
from app.reasoning.calc_review import review_calculations
from app.reasoning.evidence import Evidence
from app.reasoning.investigator import investigate
from app.reasoning.reader import read_inputs
from app.services.reasoning_service import record_text
from app.verification.recalc import failures
from tests.unit.reasoning.fakes import CFG, scripted
from tests.unit.reasoning.test_checkpoints import tool_model
from tests.unit.reasoning.test_reader import claim

FILE_A = "Boy1 = 1.1.2000\n236fev2 ed = 00.02.2222\nBoii1 = 1.1.2000\nGirl1 = 1.1.2001\nBoy1 = 11.18.2026\n"
FILE_B = "Boy2 = 1.1.2000\n"
YEAR = 2026


def age(birth_year: int) -> CalcRecord:
    """The engine's whole calculation: age = current year minus birth year, kept as a record with its source line."""
    return CalcRecord.model_validate({
        "id": "fig:age_boy1", "kind": "figure", "label": "age of Boy1", "formula": "year - birth",
        "inputs": [{"name": "year", "label": "current year", "value": str(YEAR), "source": "calc:clock"},
                   {"name": "birth", "label": "birth year", "value": str(birth_year), "source": "fileA.txt:1"}],
        "result": str(YEAR - birth_year)})


def brothers(tmp_path: Path, birth_year: int = 2000) -> Evidence:
    (tmp_path / "fileA.txt").write_text(FILE_A, encoding="utf-8")
    (tmp_path / "fileB.txt").write_text(FILE_B, encoding="utf-8")
    record = age(birth_year)
    return Evidence(
        data_dir=tmp_path, files=frozenset({"fileA.txt", "fileB.txt"}), last_year=YEAR,
        calculations={record.id: record_text(record)}, results={record.id: record.result},
        lineage={record.id: "fileA.txt:1: Boy1 = 1.1.2000"},
        confirmed={"sign_implausible": frozenset({record.id})} if record.result < 0 else {},
    )


def test_checkpoint_1_flags_the_four_bad_lines_and_proves_only_what_code_can(tmp_path: Path) -> None:
    flags = {"fileA.txt:2": "value_not_plausible", "fileA.txt:3": "near_miss_of_expected",
             "fileA.txt:4": "label_contradicts_meaning", "fileA.txt:5": "value_not_plausible"}
    model, _ = scripted(lambda p: {"claims": [claim(c, f, "does not fit") for c, f in flags.items()]
                                   if p["file"] == "fileA.txt" else []})
    report = read_inputs(CFG, Ledger(tmp_path / "l.jsonl"), brothers(tmp_path), "live", model)
    tiers = {f.cite: f.tier for f in report.findings}
    assert tiers == {"fileA.txt:2": "verified", "fileA.txt:3": "suspicion", "fileA.txt:4": "suspicion",
                     "fileA.txt:5": "verified"}  # month 18 and year 2222 are provable; a typo and a wrong sex are not


def test_checkpoint_2_sees_a_negative_age_and_code_has_already_rechecked_the_arithmetic(tmp_path: Path) -> None:
    evidence = brothers(tmp_path, birth_year=2027)
    assert failures([age(2027)]) == []  # 2026 - 2027 = -1 is the right sum; the sense is what is wrong
    model, _ = scripted(lambda p: {"claims": [{"cite": "fig:age_boy1", "concern": "sign_implausible",
                                               "reason": "an age cannot be negative", "quoted": ["fileA.txt:1"]}]})
    report = review_calculations(CFG, Ledger(tmp_path / "l.jsonl"), evidence, "live", model)
    assert [(f.cite, f.tier) for f in report.findings] == [("fig:age_boy1", "verified")]


def test_checkpoint_3_traces_the_age_back_to_the_line_and_never_writes_a_corrected_value(tmp_path: Path) -> None:
    evidence = brothers(tmp_path, birth_year=2027)
    model, _ = scripted(lambda p: {"claims": [{"cite": "fig:age_boy1", "concern": "sign_implausible",
                                               "reason": "negative", "quoted": []}]})
    concerns = review_calculations(CFG, Ledger(tmp_path / "a.jsonl"), evidence, "live", model)
    final: dict[str, Any] = {"chain": [{"cite": "fig:age_boy1", "note": "year 2026 minus birth 2027", "quoted": []},
                                       {"cite": "fileA.txt:1", "note": "the source line", "quoted": ["Boy1"]}],
                             "cause": "the birth year 2027 on fileA.txt line 1 is after 2026"}
    calls = [("get_lineage", {"row_id": "fig:age_boy1"}), ("read_lines", {"file": "fileA.txt", "start": 1, "end": 1})]
    tracer, _ = tool_model(calls, final)
    trace = investigate(CFG, Ledger(tmp_path / "b.jsonl"), evidence, concerns, "live", tracer).traces[0]
    assert [c for c, _ in trace.chain] == ["fig:age_boy1", "fileA.txt:1"] and "2027" in trace.cause
    assert Decimal("-1") == evidence.results["fig:age_boy1"]  # the engine's number is untouched
