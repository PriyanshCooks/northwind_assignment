"""Run registry, upload, review and build endpoints. Each calls one existing service."""
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api_models import Decisions, NewRun
from app.services import pipeline_service as pipeline
from app.services.registry_service import Registry
from app.services.upload_service import EXPECTED_FILES, MAX_BYTES, file_status, validate_bytes

router = APIRouter(prefix="/api")


def registry(request: Request) -> Registry:
    reg: Registry = request.app.state.registry
    return reg


Reg = Annotated[Registry, Depends(registry)]


@router.get("/runs")
def list_runs(reg: Reg, archived: bool = False) -> list[dict[str, Any]]:
    return reg.list(archived)


@router.post("/runs/{run_id}/archive")
def archive(run_id: str, reg: Reg) -> dict[str, Any]:
    return reg.update(run_id, archived=True)


@router.post("/runs/{run_id}/restore")
def restore(run_id: str, reg: Reg) -> dict[str, Any]:
    return reg.update(run_id, archived=False)


@router.post("/runs")
def create_run(body: NewRun, reg: Reg) -> dict[str, Any]:
    return reg.create(body.name, body.use_sample)


@router.get("/runs/{run_id}")
def open_run(run_id: str, reg: Reg) -> dict[str, Any]:
    return reg.meta(run_id) | {"files": file_status(reg.data_dir(run_id))}


@router.put("/runs/{run_id}/files/{name}")
async def upload(run_id: str, name: str, request: Request, reg: Reg) -> dict[str, Any]:
    """The body is the raw file. It is checked against its contract in a scratch copy, then stored only if it passes."""
    if name not in EXPECTED_FILES:
        raise HTTPException(422, f"{name} is not one of the 15 expected files")
    folder = reg.data_dir(run_id)
    body = await request.body()
    if len(body) > MAX_BYTES:
        raise HTTPException(413, f"{name} is larger than {MAX_BYTES} bytes")
    error = validate_bytes(name, body)
    if error is None:
        (folder / name).write_bytes(body)
    return {"name": name, "stored": error is None, "error": error}


@router.post("/runs/{run_id}/analyse")
def analyse(run_id: str, reg: Reg) -> dict[str, Any]:
    return pipeline.analyse(reg, run_id)


@router.get("/runs/{run_id}/review")
def review(run_id: str, reg: Reg) -> dict[str, Any]:
    return pipeline.review_view(reg, run_id)


@router.post("/runs/{run_id}/decisions")
def decide(run_id: str, body: Decisions, reg: Reg) -> dict[str, Any]:
    return pipeline.decide(reg, run_id, body.approver, body.decisions)


@router.post("/runs/{run_id}/build")
def build(run_id: str, reg: Reg) -> dict[str, Any]:
    return pipeline.build(reg, run_id)
