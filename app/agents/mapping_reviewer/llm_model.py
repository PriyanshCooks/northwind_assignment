"""The call: builds the prompt, calls app.llm and returns the typed answer."""
from typing import Any

from app.agents.mapping_reviewer.prompts import PROMPT_VERSION, SYSTEM
from app.agents.mapping_reviewer.schema import MappingVerdictBase, mapping_verdict_model
from app.llm.client import Mode, run_structured
from app.llm.factory import LlmConfig
from app.llm.ledger import Ledger


def review_mapping(cfg: LlmConfig, ledger: Ledger, packet: dict[str, Any], group_codes: tuple[str, ...],
                   mode: Mode = "replay") -> MappingVerdictBase:
    return run_structured(cfg, ledger, agent="mapping_reviewer", system_prompt=SYSTEM, prompt_version=PROMPT_VERSION,
                          packet=packet, schema=mapping_verdict_model(group_codes), mode=mode)
