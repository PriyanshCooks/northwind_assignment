"""Fake models for the reasoning tests: scripted answers, no network, no cost."""
import json
from collections.abc import Callable
from typing import Any

from pydantic_ai import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.llm.factory import LlmConfig

CFG = LlmConfig(model="ollama:test", ledger="ledger/test.jsonl", max_output_tokens=400,
                ollama_base_url="http://localhost:11434/v1", settings={"temperature": 0.0, "seed": 7})


def prompt_of(messages: list[ModelMessage]) -> dict[str, Any]:
    """The packet the model was asked about."""
    for part in messages[-1].parts:
        if part.part_kind == "user-prompt":
            return json.loads(str(part.content))  # type: ignore[attr-defined,no-any-return]
    raise AssertionError("no user prompt")


def scripted(answer_for: Callable[[dict[str, Any]], dict[str, Any]]) -> tuple[FunctionModel, list[dict[str, Any]]]:
    """A model that answers each packet with answer_for(packet) and remembers what it was asked."""
    asked: list[dict[str, Any]] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        packet = prompt_of(messages)
        asked.append(packet)
        return ModelResponse(parts=[TextPart(json.dumps(answer_for(packet)))])

    return FunctionModel(respond), asked
