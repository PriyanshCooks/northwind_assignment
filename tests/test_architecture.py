"""Import boundaries from the structure document, section 5, checked on the real source tree."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"

# The engine touches numbers, so no model output and no web or model library may reach it.
ENGINE = ("core", "parsers", "detectors", "verification", "writers", "domain")
FORBIDDEN_APP = ("app.agents", "app.llm", "app.review", "app.orchestrator", "app.routes", "app.main")
FORBIDDEN_LIBS = ("fastapi", "langgraph", "pydantic_ai", "openai", "anthropic", "google")
MODEL_LIBS = ("pydantic_ai", "openai", "anthropic", "google")


def imported_modules(source: str, module: str) -> set[str]:
    """Every module a source file imports, with relative imports resolved against `module`."""
    found: set[str] = set()
    package = module.split(".")[:-1]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            base = package[: len(package) - node.level + 1] if node.level else []
            name = ".".join([*base, *(node.module.split(".") if node.module else [])])
            found.add(name)
            found |= {f"{name}.{alias.name}" for alias in node.names}
    return found


def source_files(folder: str) -> list[Path]:
    return sorted(p for p in (APP / folder).rglob("*.py") if "__pycache__" not in p.parts)


def banned_in(source: str, module: str, banned: tuple[str, ...]) -> list[str]:
    imports = imported_modules(source, module)
    return sorted(m for m in imports if any(m == b or m.startswith(b + ".") for b in banned))


def hits(path: Path, banned: tuple[str, ...]) -> list[str]:
    module = ".".join(path.relative_to(ROOT).with_suffix("").parts)
    return banned_in(path.read_text(encoding="utf-8"), module, banned)


def violations(folders: tuple[str, ...], banned: tuple[str, ...]) -> list[str]:
    found = []
    for folder in folders:
        for path in source_files(folder):
            found += [f"{path.relative_to(ROOT).as_posix()} imports {m}" for m in hits(path, banned)]
    return found


def test_engine_never_imports_ai_or_web_code() -> None:
    assert violations(ENGINE, FORBIDDEN_APP) == []


def test_engine_imports_no_web_or_model_library() -> None:
    assert violations(ENGINE, FORBIDDEN_LIBS) == []


def test_agents_never_import_core() -> None:
    assert violations(("agents", "reasoning"), ("app.core",)) == []


def test_only_the_llm_folder_imports_a_model_library() -> None:
    others = tuple(p.name for p in APP.iterdir() if p.is_dir() and p.name not in ("llm", "__pycache__"))
    assert violations(others, MODEL_LIBS) == []
    assert hits(APP / "main.py", MODEL_LIBS) == []


def test_only_the_db_folder_imports_sqlite3() -> None:
    others = tuple(p.name for p in APP.iterdir() if p.is_dir() and p.name not in ("db", "__pycache__"))
    assert violations(others, ("sqlite3",)) == []


def test_checker_resolves_relative_and_absolute_imports() -> None:
    source = "import fastapi\nfrom app.llm import client\nfrom ..agents import x\nfrom . import y\n"
    found = imported_modules(source, "app.core.translate")
    assert {"fastapi", "app.llm", "app.llm.client", "app.agents", "app.agents.x", "app.core.y"} <= found


def test_checker_catches_a_forbidden_import() -> None:
    source = "from app.llm.client import run_structured\nimport openai\n"
    assert "app.llm.client" in banned_in(source, "app.core.translate", FORBIDDEN_APP)
    assert banned_in(source, "app.core.translate", FORBIDDEN_LIBS) == ["openai"]
    assert banned_in("import json\n", "app.core.translate", FORBIDDEN_LIBS) == []
