"""작업 큐 관리"""

import threading
from automation.models import Job, JobStatus


class QueueManager:
    def __init__(self):
        self._jobs: list[Job] = []
        self._lock = threading.Lock()

    @property
    def jobs(self) -> list[Job]:
        with self._lock:
            return list(self._jobs)

    def add_job(self, job: Job) -> bool:
        """작업 추가. 이미 있으면 False 반환."""
        with self._lock:
            for existing in self._jobs:
                if existing.book_dir == job.book_dir:
                    return False
            self._jobs.append(job)
            return True

    def remove_missing_jobs(self):
        """폴더가 삭제된 대기중 작업을 큐에서 제거"""
        with self._lock:
            self._jobs = [
                j for j in self._jobs
                if j.status != JobStatus.WAITING or j.book_dir.exists()
            ]

    def get_next_job(self) -> Job | None:
        """다음 대기중인 작업 반환"""
        with self._lock:
            for job in self._jobs:
                if job.status == JobStatus.WAITING:
                    return job
        return None
