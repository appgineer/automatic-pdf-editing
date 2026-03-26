"""파이프라인 실행"""

import gc
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

        tmp_dir = tempfile.mkdtemp()
        try:
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
        finally:
            # Windows: fitz 파일 핸들 해제 후 임시 폴더 삭제
            gc.collect()
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

        self._notify()

    def _run_pipeline(self, job: Job, tmp: Path):
        pdf_files = job.get_pdf_files()
        config = job.config

        # --- 임시 비활성화: 합치기, 레벨, 분할 ---
        # # 1. PDF 합치기
        # job.current_step = "PDF 합치기"
        # self._notify()
        # merged_path = tmp / f"{job.book_name}_merged.pdf"
        # merge_pdfs(pdf_files, merged_path)
        # current_pdf = merged_path

        # # 2. 레벨 조정 (고급일 때만)
        # if config.scan_type == "고급":
        #     job.current_step = "레벨 조정"
        #     self._notify()
        #     leveled_path = tmp / f"{job.book_name}_leveled.pdf"
        #     apply_levels_to_pdf(current_pdf, leveled_path, config.black_point, config.white_point)
        #     current_pdf = leveled_path

        # --- OCR만 실행: 입력 폴더의 원본 PDF → 출력 폴더 ---
        output_dir = self._get_output_dir(job)
        output_dir.mkdir(parents=True, exist_ok=True)

        if config.ocr:
            job.current_step = "OCR 처리중"
            self._notify()
            for pdf_file in pdf_files:
                run_ocr(pdf_file, pdf_file, config.ocr_language)
                # _OCR.pdf 파일은 원본과 같은 폴더에 자동 생성됨
        else:
            # OCR 안 함: 원본 그대로 출력 폴더에 복사
            for pdf_file in pdf_files:
                shutil.copy2(pdf_file, output_dir / pdf_file.name)

        # --- 임시 비활성화: 최종 분할 ---
        # final_files = []
        #
        # if config.is_split and config.split_method == "page" and config.split_page_ranges:
        #     job.current_step = "페이지 범위 분할"
        #     self._notify()
        #     final_files = split_pdf_by_page_ranges(current_pdf, config.split_page_ranges, output_dir)
        # elif config.is_split and config.split_method == "size" and config.split_size_mb > 0:
        #     job.current_step = "크기 기준 분할"
        #     self._notify()
        #     final_files = split_pdf_by_size(current_pdf, config.split_size_mb, output_dir)
        # else:
        #     # 분할 없이 최종 파일 복사
        #     final_path = output_dir / f"{job.book_name}.pdf"
        #     shutil.copy2(current_pdf, final_path)
        #     final_files = [final_path]

        # 분할된 파일이 tmp에 있으면 output으로 이동
        final_files = []
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
