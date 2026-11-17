"""The model comes from config/llm.toml: a string like ollama:<name> or openai:<name>, plus its settings."""
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_ai.models import Model, infer_model

from app.utils.paths import CONFIG_DIR, ROOT


class LlmConfig(BaseModel):
    model: str
    ledger: str
    max_output_tokens: int
    ollama_base_url: str
    settings: dict[str, float | int | str] = {}

    @property
    def ledger_path(self) -> Path:
        return ROOT / self.ledger


def load_llm_config(path: Path = CONFIG_DIR / "llm.toml") -> LlmConfig:
    section = tomllib.loads(path.read_text(encoding="utf-8"))["llm"]
    return LlmConfig(**{k: v for k, v in section.items() if k != "settings"}, settings=section.get("settings", {}))


def model_settings(cfg: LlmConfig) -> dict[str, Any]:
    """Only what config lists is sent (a cloud model may reject temperature or seed), plus the output cap."""
    return {"max_tokens": cfg.max_output_tokens, **cfg.settings}


def build_model(cfg: LlmConfig) -> Model:
    provider, _, name = cfg.model.partition(":")
    if provider == "ollama":
        from pydantic_ai.models.openai import OpenAIChatModel  # needs the openai package (requirements-llm.txt)
        from pydantic_ai.providers.openai import OpenAIProvider

        return OpenAIChatModel(name, provider=OpenAIProvider(base_url=cfg.ollama_base_url, api_key="ollama"))
    return infer_model(cfg.model)
