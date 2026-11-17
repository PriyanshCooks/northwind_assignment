"""What we keep from a model call besides its answer, and what we switch off: no telemetry leaves the machine."""
import os
from typing import Any


def quiet_environment() -> None:
    """The only outbound traffic is the model call itself, and only in live mode."""
    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
    os.environ.setdefault("LOGFIRE_SEND_TO_LOGFIRE", "false")


def describe(result: Any) -> dict[str, Any]:
    """Stop reason and token counts of a finished run, for the ledger line."""
    usage = result.usage
    return {"stop_reason": getattr(result.response, "finish_reason", None),
            "usage": {"requests": usage.requests, "input_tokens": usage.input_tokens,
                      "output_tokens": usage.output_tokens}}
