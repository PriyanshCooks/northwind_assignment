"""The same nodes run in order without LangGraph: the fallback, and the other side of the equivalence test."""
from app.orchestrator.edges import after_analyse
from app.orchestrator.nodes import Answer, analyse, apply_answer, consolidate, export, intake
from app.orchestrator.state import RunState


def run_plain(state: RunState, answer: Answer | None = None) -> RunState:
    """With items waiting and no answer the run stops at the human gate, as the graph does when it pauses."""
    state = RunState(**{**state, **intake(state)})
    state = RunState(**{**state, **analyse(state)})
    if after_analyse(state) == "resolve":
        if answer is None:
            return RunState(**{**state, "status": "awaiting_review"})
        state = RunState(**{**state, **apply_answer(state, answer)})
    for node in (consolidate, export):
        state = RunState(**{**state, **node(state)})
    return state
