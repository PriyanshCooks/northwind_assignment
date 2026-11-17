"""Results, what-if, compare, output choice and export endpoints."""
from typing import Any

from fastapi import APIRouter, HTTPException, Response

from app.api_models import Outputs, WhatIf
from app.routes import Reg
from app.services import output_service as files
from app.services import pipeline_service as pipeline
from app.services import results_service as results
from app.services.pipeline_service import NotReady
from app.services.whatif_service import Change, patched_copy

router = APIRouter(prefix="/api")


def _finished(reg: Reg, run_id: str) -> None:
    if reg.meta(run_id)["status"] != "done":
        raise NotReady("the run has not finished")


@router.get("/runs/{run_id}/results")
def get_results(run_id: str, reg: Reg) -> dict[str, Any]:
    _finished(reg, run_id)
    out = reg.out_dir(run_id)
    items = results.issues(out)
    return {"figures": results.figures(out), "issues": items, "cards": pipeline.result_cards(reg, run_id, items)}


@router.get("/runs/{run_id}/outputs")
def get_outputs(run_id: str, reg: Reg) -> dict[str, Any]:
    _finished(reg, run_id)
    return {"available": results.available_outputs(reg.out_dir(run_id)), "chosen": reg.meta(run_id)["outputs"]}


@router.put("/runs/{run_id}/outputs")
def choose_outputs(run_id: str, body: Outputs, reg: Reg) -> dict[str, Any]:
    _finished(reg, run_id)
    results.build_zip(reg.out_dir(run_id), body.files)
    return reg.update(run_id, outputs=body.files)


@router.post("/runs/{run_id}/whatif")
def whatif(run_id: str, body: WhatIf, reg: Reg) -> dict[str, Any]:
    """A changed input becomes a new run beside the old one; the old run is never touched."""
    parent = reg.meta(run_id)
    new = reg.create(body.name or f"what-if on {parent['name']}", parent=run_id,
                     copy_config_from=reg.config_dir(run_id))
    try:
        patched_copy(reg.data_dir(run_id), reg.data_dir(new["id"]), Change(body.patches, body.appends))
    except (ValueError, IndexError, KeyError, OSError) as error:
        raise HTTPException(422, f"change could not be applied: {error}") from error
    return pipeline.analyse(reg, new["id"])


@router.get("/runs/{run_id}/compare/{other_id}")
def compare(run_id: str, other_id: str, reg: Reg) -> dict[str, Any]:
    _finished(reg, run_id)
    _finished(reg, other_id)
    return results.compare(reg, run_id, other_id)


@router.get("/runs/{run_id}/export")
def export(run_id: str, reg: Reg) -> Response:
    _finished(reg, run_id)
    chosen = reg.meta(run_id)["outputs"] or [o["name"] for o in results.available_outputs(reg.out_dir(run_id))]
    return Response(results.build_zip(reg.out_dir(run_id), chosen), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{run_id}.zip"'})


@router.get("/runs/{run_id}/output-files")
def output_files(run_id: str, reg: Reg) -> list[dict[str, Any]]:
    _finished(reg, run_id)
    return files.file_list(reg.out_dir(run_id))


@router.get("/runs/{run_id}/output-files/{name}")
def output_file(run_id: str, name: str, reg: Reg) -> dict[str, Any]:
    _finished(reg, run_id)
    try:
        return files.file_view(reg.out_dir(run_id), name)
    except files.TooLarge as error:
        raise HTTPException(413, str(error)) from error


@router.get("/runs/{run_id}/output-files/{name}/issues")
def output_file_issues(run_id: str, name: str, reg: Reg) -> dict[str, list[dict[str, Any]]]:
    _finished(reg, run_id)
    out = reg.out_dir(run_id)
    cards = pipeline.result_cards(reg, run_id, results.issues(out))
    return files.issues_by_file(out, cards, name)


@router.get("/runs/{run_id}/output-files/{name}/download")
def output_download(run_id: str, name: str, reg: Reg) -> Response:
    _finished(reg, run_id)
    out = reg.out_dir(run_id)
    if name not in {o["name"] for o in results.available_outputs(out)}:
        raise HTTPException(404, f"not an output of this run: {name}")
    return Response((out / name).read_bytes(), media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
