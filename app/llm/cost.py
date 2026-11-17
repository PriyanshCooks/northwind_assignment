"""What a recorded call cost, from config/pricing.toml. An estimate for the review report: no figure depends on it."""
import tomllib
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.utils.paths import CONFIG_DIR

MILLION = Decimal(1_000_000)


def load_prices(path: Path = CONFIG_DIR / "pricing.toml") -> dict[str, dict[str, str]]:
    return tomllib.loads(path.read_text(encoding="utf-8")).get("models", {})


def cost_fields(model: str, usage: dict[str, Any], prices: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
    """cost_usd as a string (null when the model has no price) and the reason when it is null."""
    price = (prices if prices is not None else load_prices()).get(model)
    if price is None:
        return {"cost_usd": None, "cost_note": f"no price for {model} in config/pricing.toml"}
    cost = (Decimal(usage["input_tokens"]) * Decimal(price["input_per_million"])
            + Decimal(usage["output_tokens"]) * Decimal(price["output_per_million"])) / MILLION
    return {"cost_usd": str(cost.quantize(Decimal("0.000001"))), "cost_note": f"price status {price['status']}"}


@dataclass
class AgentCost:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    recorded_cost: Decimal = Decimal(0)
    new_cost: Decimal = Decimal(0)
    unpriced: int = 0
    new_calls: int = 0


@dataclass
class CostReport:
    per_agent: dict[str, AgentCost] = field(default_factory=dict)

    def total(self) -> AgentCost:
        whole = AgentCost()
        for a in self.per_agent.values():
            whole.calls += a.calls
            whole.new_calls += a.new_calls
            whole.input_tokens += a.input_tokens
            whole.output_tokens += a.output_tokens
            whole.recorded_cost += a.recorded_cost
            whole.new_cost += a.new_cost
            whole.unpriced += a.unpriced
        return whole


def build_report(entries: list[dict[str, Any]], new_keys: set[str]) -> CostReport:
    """The entries a run used. recorded_cost is what they cost when recorded; new_cost is only what this run spent."""
    report = CostReport()
    for entry in entries:
        row = report.per_agent.setdefault(entry["agent"], AgentCost())
        usage = entry.get("usage") or {"input_tokens": 0, "output_tokens": 0}
        row.calls += 1
        row.input_tokens += usage["input_tokens"]
        row.output_tokens += usage["output_tokens"]
        cost = entry["cost_usd"] if "cost_usd" in entry else cost_fields(entry["model"], usage)["cost_usd"]
        if cost is None:
            row.unpriced += entry.get("usage") is not None
            continue
        row.recorded_cost += Decimal(cost)
        if entry["key"] in new_keys:
            row.new_cost += Decimal(cost)
    for entry in entries:
        if entry["key"] in new_keys:
            report.per_agent[entry["agent"]].new_calls += 1
    return report


def format_report(report: CostReport, model: str) -> list[str]:
    lines = [f"cost for {model} (an estimate from config/pricing.toml)"]
    for name, a in [*sorted(report.per_agent.items()), ("all agents", report.total())]:
        unpriced = f", {a.unpriced} calls without a price (cost null)" if a.unpriced else ""
        lines.append(f"  {name}: {a.calls} calls ({a.new_calls} new), {a.input_tokens} input and {a.output_tokens} "
                     f"output tokens, recorded cost ${a.recorded_cost}, new cost this run ${a.new_cost}{unpriced}")
    return lines
