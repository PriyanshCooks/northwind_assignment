"""A live reasoning command must end the process with exit code 0 once its summary is printed."""
import subprocess
import sys
import textwrap
from pathlib import Path

from app.utils.paths import ROOT

SCRIPT = """
import sys
sys.path.insert(0, {root!r})
import run
import app.cli as cli
import app.cli_review as review
from tests.unit.agents.reasoning.fakes import CFG, scripted
from tests.unit.agents.reasoning.test_guardrails import layer_answer
from app.services.reasoning_service import run_reasoning

model, _ = scripted(layer_answer)
review.load_llm_config = lambda: CFG.model_copy(update={{"model": "openai:test", "ledger": {ledger!r}}})
real = review.run_reasoning
review.run_reasoning = lambda r, c, l, mode, _m, n, smoke: real(r, c, l, mode, model, n, smoke)
run.finish(cli.main(["smoke"]))
"""


def test_the_smoke_command_prints_its_summary_and_exits_with_code_0(tmp_path: Path) -> None:
    code = textwrap.dedent(SCRIPT).format(root=str(ROOT), ledger=str(tmp_path / "l.jsonl"))
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT, timeout=120)
    assert done.returncode == 0, done.stderr[-300:]
    assert "3 units sent to openai:test" in done.stdout
