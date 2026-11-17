"""The call: builds the prompt, calls app.llm and returns the typed answer."""
from typing import Any

from app.agents.journal_reviewer.prompts import PROMPT_VERSION, SYSTEM
from app.agents.journal_reviewer.schema import JournalVerdict
from app.llm.client import Mode, run_structured
from app.llm.factory import LlmConfig
from app.llm.ledger import Ledger


def review_journal(cfg: LlmConfig, ledger: Ledger, packet: dict[str, Any], mode: Mode = "replay") -> JournalVerdict:
    return run_structured(cfg, ledger, agent="journal_reviewer", system_prompt=SYSTEM, prompt_version=PROMPT_VERSION,
                          packet=packet, schema=JournalVerdict, mode=mode)
