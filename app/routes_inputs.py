"""Input workbench endpoints: a file's rows with their findings, and the explanation of one row."""
from typing import Any

from fastapi import APIRouter, HTTPException

from app.routes import Reg
from app.services import inputs_service as inputs

router = APIRouter(prefix="/api")


@router.get("/runs/{run_id}/inputs/{name}/rows")
def rows(run_id: str, name: str, reg: Reg) -> dict[str, Any]:
    try:
        return inputs.rows_view(reg, run_id, name)
    except inputs.NoSuchFile as error:
        raise HTTPException(404, str(error)) from error


@router.get("/runs/{run_id}/inputs/{name}/rows/{line}/explain")
def explain(run_id: str, name: str, line: int, reg: Reg) -> dict[str, Any]:
    try:
        return inputs.explain_row(reg, run_id, name, line)
    except inputs.NoSuchFile as error:
        raise HTTPException(404, str(error)) from error
