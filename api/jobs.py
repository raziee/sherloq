import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class JobRecord:
    id: str
    tool: str
    status: str = "queued"
    result: dict[str, Any] | None = None
    error: str | None = None


class JobManager:
    def __init__(self, max_workers: int = 2):
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="sherloq-job")

    def submit(self, tool: str, worker: Callable[[], dict[str, Any]]) -> JobRecord:
        job_id = uuid.uuid4().hex
        record = JobRecord(id=job_id, tool=tool, status="running")
        with self._lock:
            self._jobs[job_id] = record

        def run():
            try:
                result = worker()
                with self._lock:
                    record.status = "completed"
                    record.result = result
            except Exception as exc:
                with self._lock:
                    record.status = "failed"
                    record.error = str(exc)

        self._executor.submit(run)
        return record

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)


job_manager = JobManager()
