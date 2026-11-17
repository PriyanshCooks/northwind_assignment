"""The LangGraph workflow: intake, analyse, resolve (a real pause for a person), consolidate, export."""
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.db.checkpoint import open_checkpointer
from app.orchestrator.edges import after_analyse
from app.orchestrator.nodes import Answer, analyse, apply_answer, consolidate, export, intake
from app.orchestrator.state import RunState
from app.services.run_service import input_hash
from app.utils.paths import CONFIG_DIR


def resolve(state: RunState) -> RunState:
    """Pauses until a person answers. Nothing runs before interrupt(): on resume this node starts again from the top."""
    answer = interrupt({"run_id": state["run_id"], "open_items": state["open_items"]})
    return apply_answer(state, answer)


def build_graph(checkpointer: SqliteSaver) -> Any:
    builder = StateGraph(RunState)
    for name, node in (("intake", intake), ("analyse", analyse), ("resolve", resolve),
                       ("consolidate", consolidate), ("export", export)):
        builder.add_node(name, node)
    builder.add_edge(START, "intake")
    builder.add_edge("intake", "analyse")
    builder.add_conditional_edges("analyse", after_analyse, {"resolve": "resolve", "consolidate": "consolidate"})
    builder.add_edge("resolve", "consolidate")
    builder.add_edge("consolidate", "export")
    builder.add_edge("export", END)
    return builder.compile(checkpointer=checkpointer)


def thread_for(data_dir: Path, config_dir: Path = CONFIG_DIR) -> str:
    """Data and config together, so an approved override gets its own thread and a second process finds the same one."""
    return "run-" + input_hash(data_dir, config_dir)[:16]


def _settle(graph: Any, result: dict[str, Any], config: dict[str, Any]) -> RunState:
    state = RunState(**graph.get_state(config).values)
    if "__interrupt__" in result:
        state["status"] = "awaiting_review"
    return state


def run_graph(state: RunState, checkpoint_path: Path) -> RunState:
    graph = build_graph(open_checkpointer(checkpoint_path))
    config = {"configurable": {"thread_id": thread_for(Path(state["data_dir"]), Path(state["config_dir"]))}}
    return _settle(graph, graph.invoke(state, config), config)


def resume_graph(thread_id: str, answer: Answer, checkpoint_path: Path) -> RunState:
    graph = build_graph(open_checkpointer(checkpoint_path))
    config = {"configurable": {"thread_id": thread_id}}
    return _settle(graph, graph.invoke(Command(resume=answer), config), config)
