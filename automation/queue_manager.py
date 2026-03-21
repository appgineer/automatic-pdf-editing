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

    def get_next_job(self) -> Job | None:
        """다음 대기중인 작업 반환"""
        with self._lock:
            for job in self._jobs:
                if job.status == JobStatus.WAITING:
                    return job
        return None

    def move_up(self, job: Job):
        """대기중인 작업을 위로 이동"""
        with self._lock:
            if job.status != JobStatus.WAITING:
                return
            idx = self._jobs.index(job)
            # 바로 위의 대기중인 항목 찾기
            for i in range(idx - 1, -1, -1):
                if self._jobs[i].status == JobStatus.WAITING:
                    self._jobs[idx], self._jobs[i] = self._jobs[i], self._jobs[idx]
                    break

    def move_down(self, job: Job):
        """대기중인 작업을 아래로 이동"""
        with self._lock:
            if job.status != JobStatus.WAITING:
                return
            idx = self._jobs.index(job)
            for i in range(idx + 1, len(self._jobs)):
                if self._jobs[i].status == JobStatus.WAITING:
                    self._jobs[idx], self._jobs[i] = self._jobs[i], self._jobs[idx]
                    break

    def get_customer_jobs(self, customer_name: str) -> list[Job]:
        """특정 고객의 모든 작업 반환"""
        with self._lock:
            return [j for j in self._jobs if j.customer_name == customer_name]

    def all_customer_done(self, customer_name: str) -> bool:
        """고객의 모든 작업이 완료되었는지 확인"""
        jobs = self.get_customer_jobs(customer_name)
        return len(jobs) > 0 and all(j.status == JobStatus.DONE for j in jobs)
