"""Routing shared by both runners: the human gate is only entered when something is waiting for a person."""
from app.orchestrator.state import RunState


def after_analyse(state: RunState) -> str:
    return "resolve" if state.get("open_items") else "consolidate"
