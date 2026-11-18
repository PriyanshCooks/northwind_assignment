"""The investigator may cite a step in any id form the tools print; an id nothing returned is dropped."""
import pytest

from app.domain.runs import Context
from app.reasoning.evidence import Evidence
from app.reasoning.grounding import cite_exists
from app.reasoning.investigator import ground_investigation
from app.reasoning.schema import Investigation
from app.services.reasoning_service import build_evidence
from app.services.run_service import stage


@pytest.fixture(scope="module")
def evidence(ctx: Context) -> Evidence:
    return build_evidence(stage(ctx))


VALID = ["tb_uk.csv:3", "tb_uk.csv:2-5", "calc:row:1200", "row:1200", "lineage row:1200", "fig:total_assets",
         "calc:fig:total_assets", "policy 2", "rule policy 2", "account 4100"]
INVENTED = ["row:9999", "calc:fig:invented", "lineage row:9999", "policy 99", "account 9999", "tb_uk.csv:9999",
            "tb_uk.csv:5-2", "nothing.csv:1", "tb_uk.csv", "calc:"]


@pytest.mark.parametrize("cite", VALID)
def test_a_valid_trace_step_survives_in_every_id_form(evidence: Evidence, cite: str) -> None:
    answer = Investigation.model_validate({"chain": [{"cite": cite, "note": "the source row", "quoted": []}]})
    trace = ground_investigation("fig:total_assets", answer, "{}", [], evidence)
    assert [c for c, _ in trace.chain] == [cite] and trace.dropped == ()


@pytest.mark.parametrize("cite", INVENTED)
def test_an_invented_id_is_dropped(evidence: Evidence, cite: str) -> None:
    assert not cite_exists(cite, evidence)
    answer = Investigation.model_validate({"chain": [{"cite": cite, "note": "made up", "quoted": []}]})
    trace = ground_investigation("fig:total_assets", answer, "{}", [], evidence)
    assert trace.chain == () and trace.dropped[0].why == "the cited line or calculation does not exist"
