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

    def move_customer_up(self, customer_name: str):
        """고객의 모든 작업을 통째로 위로 이동"""
        with self._lock:
            customer_jobs = [j for j in self._jobs if j.customer_name == customer_name]
            if not customer_jobs or not all(j.status == JobStatus.WAITING for j in customer_jobs):
                return

            first_idx = self._jobs.index(customer_jobs[0])
            if first_idx == 0:
                return

            # 바로 위 고객의 작업들 찾기
            prev_customer = self._jobs[first_idx - 1].customer_name
            prev_jobs = [j for j in self._jobs if j.customer_name == prev_customer]
            if not all(j.status == JobStatus.WAITING for j in prev_jobs):
                return

            # 위 고객 작업들을 제거하고 현재 고객 뒤에 삽입
            for j in prev_jobs:
                self._jobs.remove(j)
            insert_idx = self._jobs.index(customer_jobs[-1]) + 1
            for i, j in enumerate(prev_jobs):
                self._jobs.insert(insert_idx + i, j)

    def move_customer_down(self, customer_name: str):
        """고객의 모든 작업을 통째로 아래로 이동"""
        with self._lock:
            customer_jobs = [j for j in self._jobs if j.customer_name == customer_name]
            if not customer_jobs or not all(j.status == JobStatus.WAITING for j in customer_jobs):
                return

            last_idx = self._jobs.index(customer_jobs[-1])
            if last_idx >= len(self._jobs) - 1:
                return

            # 바로 아래 고객의 작업들 찾기
            next_customer = self._jobs[last_idx + 1].customer_name
            next_jobs = [j for j in self._jobs if j.customer_name == next_customer]
            if not all(j.status == JobStatus.WAITING for j in next_jobs):
                return

            # 아래 고객 작업들을 제거하고 현재 고객 앞에 삽입
            for j in next_jobs:
                self._jobs.remove(j)
            insert_idx = self._jobs.index(customer_jobs[0])
            for i, j in enumerate(next_jobs):
                self._jobs.insert(insert_idx + i, j)

