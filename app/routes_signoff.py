"""Choose outputs before generating, sign off the generated files, and read the calculation behind an output row."""
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.routes import Reg
from app.services import calculation_service, signoff_service
from app.services import pipeline_service as pipeline
from app.services import results_service as results
from app.services.run_service import OUTPUT_FILES

router = APIRouter(prefix="/api")
TARGET = re.compile(r"^[A-Za-z0-9_.-]{1,60}$")


class Mark(BaseModel):
    file: str
    reviewer: str
    row: str | None = None  # a row mark, bound to the file's hash; none means the whole file


class Plan(BaseModel):
    files: list[str]


@router.get("/runs/{run_id}/output-plan")
def get_plan(run_id: str, reg: Reg) -> dict[str, Any]:
    """The nine output files, known before anything is generated, and the ones chosen so far."""
    meta = reg.meta(run_id)
    if meta["status"] == "new":
        raise HTTPException(409, "scan the files first: nothing has been analysed yet")
    return {"available": [{"name": n, "required": n == results.ALWAYS} for n in [*OUTPUT_FILES, results.ALWAYS]],
            "chosen": meta["outputs"]}


@router.put("/runs/{run_id}/output-plan")
def set_plan(run_id: str, body: Plan, reg: Reg) -> dict[str, Any]:
    allowed = {*OUTPUT_FILES, results.ALWAYS}
    unknown = sorted(set(body.files) - allowed)
    if unknown:
        raise HTTPException(422, "not an output file: " + ", ".join(unknown))
    if reg.meta(run_id)["status"] == "new":
        raise HTTPException(409, "scan the files first: nothing has been analysed yet")
    order = [*OUTPUT_FILES, results.ALWAYS]
    return reg.update(run_id, outputs=sorted({*body.files, results.ALWAYS}, key=order.index))


@router.get("/runs/{run_id}/signoff")
def get_signoff(run_id: str, reg: Reg) -> dict[str, Any]:
    pipeline.require_done(reg, run_id)
    return signoff_service.status(reg, run_id)


@router.post("/runs/{run_id}/signoff")
def mark_reviewed(run_id: str, body: Mark, reg: Reg) -> dict[str, Any]:
    pipeline.require_done(reg, run_id)
    try:
        return signoff_service.mark(reg, run_id, body.file, body.reviewer, body.row)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.get("/runs/{run_id}/calculation/{target}")
def get_calculation(run_id: str, target: str, reg: Reg) -> dict[str, Any]:
    pipeline.require_done(reg, run_id)
    if not TARGET.match(target):
        raise HTTPException(422, "not a figure key or account code")
    found = calculation_service.calculation(reg, run_id, target)
    if found is None:
        raise HTTPException(404, f"no calculation was recorded for {target}")
    return found
