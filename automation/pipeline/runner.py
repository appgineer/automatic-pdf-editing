"""파이프라인 실행"""

import logging
import shutil
import threading
import tempfile
from pathlib import Path

from automation.models import Job, JobStatus
from automation.queue_manager import QueueManager
from automation.pipeline.merge import merge_pdfs
from automation.pipeline.levels import apply_levels_to_pdf
from automation.pipeline.split import split_pdf_by_count, split_pdf_by_page_ranges, split_pdf_by_size
from automation.pipeline.ocr import run_ocr
from automation.pipeline.compress import create_customer_zip

logger = logging.getLogger(__name__)

OCR_SPLIT_PAGES = 100  # OCR 전 분할 단위


class PipelineRunner:
    def __init__(self, queue: QueueManager, output_folder: Path, on_update=None):
        self.queue = queue
        self.output_folder = output_folder
        self.on_update = on_update
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=30)

    def _notify(self):
        if self.on_update:
            self.on_update()

    def _run_loop(self):
        import time
        while self._running:
            job = self.queue.get_next_job()
            if job:
                self._process_job(job)
            else:
                time.sleep(1)

    def _process_job(self, job: Job):
        job.status = JobStatus.RUNNING
        self._notify()

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp = Path(tmp_dir)
                self._run_pipeline(job, tmp)

            job.status = JobStatus.DONE
            job.current_step = "완료"
            logger.info(f"작업 완료: {job.display_name}")

            # 고객의 모든 책 완료 시 ZIP 생성
            if self.queue.all_customer_done(job.customer_name):
                self._create_zip(job.customer_name)

        except Exception as e:
            job.status = JobStatus.ERROR
            job.error_message = str(e)
            job.current_step = f"오류: {e}"
            logger.error(f"작업 오류: {job.display_name} - {e}")

        self._notify()

    def _run_pipeline(self, job: Job, tmp: Path):
        pdf_files = job.get_pdf_files()
        config = job.config

        # 1. PDF 합치기
        job.current_step = "PDF 합치기"
        self._notify()
        merged_path = tmp / f"{job.book_name}_merged.pdf"
        merge_pdfs(pdf_files, merged_path)
        current_pdf = merged_path

        # 2. 레벨 조정 (고급일 때만)
        if config.type == "고급":
            job.current_step = "레벨 조정"
            self._notify()
            leveled_path = tmp / f"{job.book_name}_leveled.pdf"
            apply_levels_to_pdf(current_pdf, leveled_path, config.black_point, config.white_point)
            current_pdf = leveled_path

        # 3. 100페이지 분할 (OCR용)
        job.current_step = "OCR용 분할"
        self._notify()
        split_parts = split_pdf_by_count(current_pdf, OCR_SPLIT_PAGES, tmp, suffix="_s")

        # 4. ABBYY OCR
        job.current_step = "OCR 처리중"
        self._notify()
        ocr_results = []
        for part in split_parts:
            ocr_out = tmp / f"{part.stem}_OCR.pdf"
            run_ocr(part, ocr_out, config.ocr_language)
            ocr_results.append(ocr_out)

        # 5. OCR 결과 합치기
        if len(ocr_results) > 1:
            job.current_step = "OCR 결과 합치기"
            self._notify()
            final_merged = tmp / f"{job.book_name}_OCR.pdf"
            merge_pdfs(ocr_results, final_merged)
            current_pdf = final_merged
        else:
            current_pdf = ocr_results[0]

        # 6. 최종 분할 (config에 따라)
        output_dir = self._get_output_dir(job)
        output_dir.mkdir(parents=True, exist_ok=True)

        final_files = []

        if config.split_after_ocr and config.split_by_pages:
            job.current_step = "페이지 범위 분할"
            self._notify()
            final_files = split_pdf_by_page_ranges(current_pdf, config.split_by_pages, output_dir)
        elif config.split_after_ocr and config.split_by_size > 0:
            job.current_step = "크기 기준 분할"
            self._notify()
            final_files = split_pdf_by_size(current_pdf, config.split_by_size, output_dir)
        else:
            # 분할 없이 최종 파일 복사
            final_path = output_dir / f"{job.book_name}.pdf"
            shutil.copy2(current_pdf, final_path)
            final_files = [final_path]

        # 분할된 파일이 tmp에 있으면 output으로 이동
        for f in final_files:
            if str(f).startswith(str(tmp)):
                dest = output_dir / f.name
                shutil.copy2(f, dest)

    def _get_output_dir(self, job: Job) -> Path:
        return self.output_folder / job.customer_name / job.book_name

    def _create_zip(self, customer_name: str):
        """고객의 모든 완료된 책을 ZIP으로 압축"""
        customer_dir = self.output_folder / customer_name
        if not customer_dir.exists():
            return

        all_files = []
        for pdf_file in customer_dir.rglob("*.pdf"):
            all_files.append(pdf_file)

        if all_files:
            create_customer_zip(customer_name, all_files, self.output_folder)
            logger.info(f"ZIP 생성: {customer_name} 님.zip")
