"""Job manager: tracks active pipeline tasks and enforces single-session lock."""
import asyncio
from typing import Optional


class JobManager:
    def __init__(self) -> None:
        self._active_run_id: Optional[str] = None
        self._lock = asyncio.Lock()

    @property
    def active_run_id(self) -> Optional[str]:
        return self._active_run_id

    @property
    def is_busy(self) -> bool:
        return self._active_run_id is not None

    async def acquire(self, run_id: str) -> bool:
        async with self._lock:
            if self._active_run_id is not None:
                return False
            self._active_run_id = run_id
            return True

    async def release(self, run_id: str) -> None:
        async with self._lock:
            if self._active_run_id == run_id:
                self._active_run_id = None


job_manager = JobManager()
