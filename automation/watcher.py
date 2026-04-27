"""폴더 감시 (폴링 방식)"""

import time
import threading
import logging
from pathlib import Path
from automation.models import Job, BookConfig, parse_customer_folder
from automation.queue_manager import QueueManager

logger = logging.getLogger(__name__)

POLL_INTERVAL = 5  # 초
STABLE_CHECK_INTERVAL = 10  # 초


class FolderWatcher:
    def __init__(self, queue: QueueManager, on_new_job=None):
        self.queue = queue
        self.on_new_job = on_new_job
        self.input_folder: Path | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._known_sizes: dict[str, int] = {}  # 파일 안정성 체크용

    def scan_once(self, input_folder: Path):
        """폴더를 한 번만 스캔하여 리스트 등록 (작업 시작 없이)"""
        self.input_folder = input_folder
        self.queue.remove_missing_jobs()
        self._scan_folder(skip_stable_check=True)

    def start(self, input_folder: Path):
        self.input_folder = input_folder
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)

    def _poll_loop(self):
        while self._running:
            try:
                self._scan_folder()
            except Exception as e:
                logger.error(f"폴더 감시 오류: {e}")
            time.sleep(POLL_INTERVAL)

    def _scan_folder(self, skip_stable_check=False):
        if not self.input_folder or not self.input_folder.exists():
            return

        # 입력폴더/고객이름[-N]/책이름/ 구조 탐색
        for customer_dir in self.input_folder.iterdir():
            if not customer_dir.is_dir() or customer_dir.name.startswith("."):
                continue

            customer_name, expected_count = parse_customer_folder(customer_dir.name)
            book_dirs = [d for d in customer_dir.iterdir()
                         if d.is_dir() and not d.name.startswith(".")]
            if expected_count is None:
                expected_count = len(book_dirs)

            for book_dir in book_dirs:
                config_path = book_dir / "config.json"
                pdf_files = sorted(book_dir.glob("*.pdf"))

                if not config_path.exists() or not pdf_files:
                    continue

                # 파일 안정성 체크 (scan_once에서는 건너뜀)
                if not skip_stable_check and not self._files_stable(pdf_files):
                    continue

                try:
                    config = BookConfig.from_file(config_path)
                except Exception as e:
                    logger.error(f"config 읽기 실패: {config_path} - {e}")
                    continue

                job = Job(
                    customer_name=customer_name,
                    book_name=book_dir.name,
                    book_dir=book_dir,
                    config=config,
                    customer_folder_name=customer_dir.name,
                    expected_count=expected_count,
                    pdf_files=pdf_files,
                )

                if self.queue.add_job(job):
                    logger.info(f"새 작업 발견: {job.display_name}")
                    if self.on_new_job:
                        self.on_new_job(job)

    def _files_stable(self, pdf_files: list[Path]) -> bool:
        """PDF 파일 크기가 변하지 않으면 안정(전송 완료)으로 판단"""
        key = str(pdf_files[0].parent)
        current_size = sum(f.stat().st_size for f in pdf_files)

        prev_size = self._known_sizes.get(key)
        self._known_sizes[key] = current_size

        if prev_size is None:
            return False  # 첫 감지, 다음 폴링에서 비교
        return current_size == prev_size
