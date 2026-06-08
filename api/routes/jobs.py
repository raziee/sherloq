from fastapi import APIRouter, HTTPException

from api.jobs import job_manager

router = APIRouter()


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    record = job_manager.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    payload = {
        "job_id": record.id,
        "tool": record.tool,
        "status": record.status,
    }
    if record.error:
        payload["error"] = record.error
    if record.result:
        payload["result"] = record.result
    return payload
