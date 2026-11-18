"""Input workbench endpoints: a file's rows with their findings, and the explanation of one row."""
from typing import Any

from fastapi import APIRouter, HTTPException

from app.api_models import RowDecision
from app.routes import Reg
from app.services import generate_service as generate
from app.services import inputs_service as inputs
from app.services import review_actions_service as actions
from app.services import row_explain_service as row_explain
from app.services.scan_service import progress as scan_progress

router = APIRouter(prefix="/api")


@router.get("/runs/{run_id}/scan")
def scan(run_id: str, reg: Reg) -> dict[str, Any]:
    return scan_progress(reg, run_id)


@router.post("/runs/{run_id}/generate")
def generate_output(run_id: str, reg: Reg) -> dict[str, Any]:
    """Always available once the run is scanned: a Draft while anything is unanswered, the normal build otherwise."""
    return generate.generate(reg, run_id)


@router.get("/runs/{run_id}/unanswered")
def unanswered(run_id: str, reg: Reg) -> dict[str, Any]:
    return generate.unanswered(reg, run_id)


@router.get("/runs/{run_id}/inputs")
def input_files(run_id: str, reg: Reg) -> list[dict[str, Any]]:
    return inputs.file_list(reg, run_id)


@router.post("/runs/{run_id}/inputs/{name}/decisions")
def decide(run_id: str, name: str, body: RowDecision, reg: Reg) -> dict[str, Any]:
    try:
        return actions.decide(reg, run_id, name, body.key, body.action, body.reviewer, body.note)
    except inputs.NoSuchFile as error:
        raise HTTPException(404, str(error)) from error


@router.get("/runs/{run_id}/inputs/{name}/rows")
def rows(run_id: str, name: str, reg: Reg) -> dict[str, Any]:
    try:
        return inputs.rows_view(reg, run_id, name)
    except inputs.NoSuchFile as error:
        raise HTTPException(404, str(error)) from error


@router.get("/runs/{run_id}/inputs/{name}/rows/{line}/explain")
def explain(run_id: str, name: str, line: int, reg: Reg) -> dict[str, Any]:
    try:
        return row_explain.explain_row(reg, run_id, name, line)
    except inputs.NoSuchFile as error:
        raise HTTPException(404, str(error)) from error
