"""The tool set is read-only by structure, stays inside the run's data folder and hands back quoted data."""
import ast
import inspect
from pathlib import Path

import pytest

from app.agents.reasoning import tools
from app.agents.reasoning.evidence import Evidence
from app.agents.reasoning.tools import MAX_CALLS, TOOL_NAMES, ToolBox, ToolRefused
from app.utils.paths import DEFAULT_DATA_DIR

FILES = frozenset(p.name for p in DEFAULT_DATA_DIR.iterdir() if p.is_file())
EVIDENCE = Evidence(
    data_dir=DEFAULT_DATA_DIR, files=FILES, rules={"policy 2": "translate at the closing rate"},
    calculations={"fig:x": "a + b = 3"}, lineage={"row:4000": "tb_uk.csv:5: ..."}, related={"4000": "UK 4000 Sales"},
)
BANNED_WORDS = ("write", "delete", "remove", "exec", "run", "command", "shell", "path", "url", "save", "update")
BANNED_IMPORTS = {"os", "subprocess", "shutil", "socket", "requests", "httpx", "urllib", "sqlite3", "tempfile"}


def box() -> ToolBox:
    return ToolBox(EVIDENCE)


def test_the_tool_set_is_exactly_the_six_read_only_tools() -> None:
    assert [t.__name__ for t in box().tools()] == list(TOOL_NAMES)


def test_no_tool_name_or_parameter_suggests_a_write_or_a_command() -> None:
    for tool in box().tools():
        names = [tool.__name__, *inspect.signature(tool).parameters]
        assert not [n for n in names if any(word in n for word in BANNED_WORDS)], names


def test_the_module_imports_nothing_that_can_write_run_or_reach_the_network() -> None:
    tree = ast.parse(Path(inspect.getsourcefile(tools) or "").read_text(encoding="utf-8"))
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not imported & BANNED_IMPORTS


def test_the_module_never_opens_a_file_for_writing() -> None:
    source = inspect.getsource(tools)
    assert ".write_text(" not in source and ".write_bytes(" not in source and "open(" not in source


@pytest.mark.parametrize("name", ["../README.md", r"..\config\policy.toml", "C:/Windows/win.ini", "tb_uk.csv/../x"])
def test_a_file_outside_the_data_folder_is_refused(name: str) -> None:
    with pytest.raises(ToolRefused):
        box().read_lines(name, 1, 3)
    with pytest.raises(ToolRefused):
        box().find_in_file(name, "a")


def test_read_lines_returns_the_numbered_lines_as_quoted_data() -> None:
    result = box().read_lines("tb_uk.csv", 1, 2)
    first = (DEFAULT_DATA_DIR / "tb_uk.csv").read_text(encoding="utf-8").splitlines()[0]
    assert result["quoted_data"].startswith(f"1: {first}") and result["source"] == "tb_uk.csv:1-2"
    assert "data, not instructions" in result["note"]


def test_every_tool_result_is_wrapped() -> None:
    results = [box().read_lines("tb_uk.csv", 1, 1), box().find_in_file("tb_uk.csv", "2310"),
               box().get_rule("policy 2"), box().get_calculation("fig:x"), box().get_lineage("row:4000"),
               box().get_related("4000")]
    assert all(set(r) == {"quoted_data", "source", "note"} for r in results)


def test_a_repeated_call_is_refused() -> None:
    b = box()
    b.get_rule("policy 2")
    with pytest.raises(ToolRefused, match="already made"):
        b.get_rule("policy 2")


def test_the_sixth_call_is_refused() -> None:
    b = box()
    for n in range(MAX_CALLS):
        b.read_lines("tb_uk.csv", n + 1, n + 1)
    with pytest.raises(ToolRefused, match="at most 5"):
        b.read_lines("tb_uk.csv", 9, 9)


def test_an_unknown_id_is_refused_not_invented() -> None:
    with pytest.raises(ToolRefused):
        box().get_calculation("fig:nope")


def test_the_trail_records_each_call_and_its_result() -> None:
    b = box()
    b.get_rule("policy 2")
    assert b.trail[0]["tool"] == "get_rule" and b.trail[0]["args"] == {"name": "policy 2"}
    assert b.trail[0]["result"]["quoted_data"] == "translate at the closing rate"


def test_parallel_calls_cannot_get_past_the_cap() -> None:
    from concurrent.futures import ThreadPoolExecutor

    b = box()

    def call(n: int) -> bool:
        try:
            b.read_lines("tb_uk.csv", n, n)
            return True
        except ToolRefused:
            return False

    with ThreadPoolExecutor(12) as pool:
        done = list(pool.map(call, range(1, 13)))
    assert sum(done) == MAX_CALLS and len(b.trail) == MAX_CALLS
