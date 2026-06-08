import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from api.jobs import job_manager
from gui.sherloq_app.services.dispatcher import analyze, get_tool

router = APIRouter()


@router.post("/analyze/{tool_id}")
async def analyze_tool(
    tool_id: str,
    image: UploadFile = File(...),
    reference: UploadFile | None = File(None),
    params: str | None = Form(None),
    image_format: str = Form("png"),
    async_mode: str | None = Form(None),
):
    try:
        tool = get_tool(tool_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    file_bytes = await image.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty image upload")

    second_bytes = None
    second_name = None
    if reference is not None:
        second_bytes = await reference.read()
        second_name = reference.filename

    if params:
        try:
            json.loads(params)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="params must be valid JSON") from exc

    if async_mode is None:
        use_async = tool.async_default
    else:
        use_async = str(async_mode).lower() in {"1", "true", "yes", "on"}
    if use_async:
        record = job_manager.submit(
            tool_id,
            lambda: analyze(
                tool_id,
                file_bytes,
                image.filename or "upload.jpg",
                params=params,
                second_file_bytes=second_bytes,
                second_filename=second_name,
                image_format=image_format,
            ),
        )
        return {
            "job_id": record.id,
            "status": record.status,
            "tool": tool_id,
            "poll_url": f"/api/v1/jobs/{record.id}",
        }

    try:
        return analyze(
            tool_id,
            file_bytes,
            image.filename or "upload.jpg",
            params=params,
            second_file_bytes=second_bytes,
            second_filename=second_name,
            image_format=image_format,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
