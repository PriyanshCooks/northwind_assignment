"""The model comes from config/llm.toml, or from NORTHWIND_MODEL: a string like ollama:<name> or openai:<name>."""
import importlib
import os
import re
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_ai.models import Model, infer_model

from app.llm.ledger import LlmStop
from app.utils.env import load_env
from app.utils.paths import CONFIG_DIR, ROOT


class LlmConfig(BaseModel):
    model: str
    ledger: str
    max_output_tokens: int
    ollama_base_url: str
    request_timeout_s: float = 60
    settings: dict[str, float | int | str] = {}

    @property
    def ledger_path(self) -> Path:
        return ROOT / self.ledger


def ledger_name(model: str) -> str:
    """One ledger file per model, named from the model string, so a cloud run never writes into the local file."""
    return "ledger/" + re.sub(r"[^a-z0-9.]+", "-", model.lower()).strip("-") + ".jsonl"


def load_llm_config(path: Path = CONFIG_DIR / "llm.toml") -> LlmConfig:
    """NORTHWIND_MODEL switches the model and nothing else: the ledger is derived from its name and the sampling
    settings come from the `cloud_settings` table (empty: determinism comes from the ledger, not from a seed)."""
    load_env()
    section = tomllib.loads(path.read_text(encoding="utf-8"))["llm"]
    fields = {k: v for k, v in section.items() if k not in ("settings", "cloud_settings")}
    override = os.environ.get("NORTHWIND_MODEL", "").strip()
    if override and override != section["model"]:
        return LlmConfig(**{**fields, "model": override, "ledger": ledger_name(override)},
                         settings=section.get("cloud_settings", {}))
    return LlmConfig(**fields, settings=section.get("settings", {}))


def model_settings(cfg: LlmConfig) -> dict[str, Any]:
    """Only what config lists is sent (a cloud model may reject temperature or seed), plus the output cap. The
    pydantic-ai OpenAI model sends max_tokens as max_completion_tokens, the name the current API expects."""
    return {"max_tokens": cfg.max_output_tokens, **cfg.settings}


def build_model(cfg: LlmConfig) -> Model:
    provider, _, name = cfg.model.partition(":")
    if provider in ("ollama", "openai"):
        key = os.environ.get("OPENAI_API_KEY", "")
        if provider == "openai" and not key:
            raise LlmStop("OPENAI_API_KEY is not set: paste it into .env (see .env.example) and run again")
        # loaded by name: openai is only in requirements-llm.txt, so a dev-only install must still type-check
        async_openai = importlib.import_module("openai").AsyncOpenAI
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        if provider == "ollama":
            client = async_openai(base_url=cfg.ollama_base_url, api_key="ollama", timeout=cfg.request_timeout_s)
        else:
            # retries are ours (client.py): the SDK would also retry a 429 that only means "out of credit"
            client = async_openai(api_key=key, timeout=cfg.request_timeout_s, max_retries=0)
        return OpenAIChatModel(name, provider=OpenAIProvider(openai_client=client))
    return infer_model(cfg.model)
