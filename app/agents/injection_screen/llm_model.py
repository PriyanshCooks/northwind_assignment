"""The call: sends only the free text of one journal to the model and returns the typed answer."""
from typing import Any

from app.agents.injection_screen.prompts import PROMPT_VERSION, SYSTEM
from app.agents.injection_screen.schema import InjectionVerdict
from app.llm.client import Mode, run_structured
from app.llm.factory import LlmConfig
from app.llm.ledger import Ledger


def screen_text(cfg: LlmConfig, ledger: Ledger, packet: dict[str, Any], mode: Mode = "replay") -> InjectionVerdict:
    return run_structured(cfg, ledger, agent="injection_screen", system_prompt=SYSTEM, prompt_version=PROMPT_VERSION,
                          packet=packet, schema=InjectionVerdict, mode=mode)
