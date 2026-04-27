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
from automation.pipeline.split import split_pdf_by_count, split_pdf_by_page_ranges, split_pdf_by_size
from automation.pipeline.ocr import run_ocr
from automation.pipeline.abbyy_editor import run_levels_only, run_levels_with_ocr
from automation.pipeline.page_utils import prepend_first_page, delete_first_page
from automation.pipeline.compress import create_customer_zip

logger = logging.getLogger(__name__)

SPLIT_PAGES = 150  # 분할 단위 (OCR, 고급 공통)


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

            # 고객 폴더 안에 N권 다 모이면 ZIP 생성
            if self._should_zip_customer(job.customer_name, job.expected_count):
                self._create_zip(job.customer_name)

        except Exception as e:
            job.status = JobStatus.ERROR
            job.error_message = str(e)
            job.current_step = f"오류: {e}"
            logger.error(f"작업 오류: {job.display_name} - {e}")
        finally:
            gc.collect()
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
                if Path(tmp_dir).exists():
                    logger.warning(f"임시폴더 삭제 실패: {tmp_dir}")
                else:
                    logger.info(f"임시폴더 삭제 완료: {tmp_dir}")
            except Exception as e:
                logger.warning(f"임시폴더 삭제 중 오류: {tmp_dir} - {e}")

        self._notify()

    def _run_pipeline(self, job: Job, tmp: Path):
        pdf_files = job.get_pdf_files()
        config = job.config
        current_pdf = pdf_files[0]

        # --- 3가지 Flow 분기 ---
        if config.scan_type == "고급" and config.ocr:
            current_pdf = self._flow_advanced_ocr(job, tmp, current_pdf)
        elif config.scan_type == "고급":
            current_pdf = self._flow_advanced_only(job, tmp, current_pdf)
        elif config.ocr:
            current_pdf = self._flow_standard_ocr(job, tmp, current_pdf)

        # --- 파일명 접미사 조합 ---
        suffix = ""
        if config.scan_type == "고급":
            suffix += "_고급"
        if config.ocr:
            suffix += "_OCR"
        final_stem = f"{job.book_name}{suffix}"

        # --- 최종 출력 (출력폴더/고객명/책명/) ---
        output_dir = self.output_folder / job.customer_name / job.book_name
        output_dir.mkdir(parents=True, exist_ok=True)

        if config.is_split and (config.split_method == "page" or config.split_method == "size"):
            # 분할 함수가 stem 기반으로 파일명을 만들므로 접미사 포함된 이름으로 복사
            named_pdf = tmp / f"{final_stem}.pdf"
            shutil.copy2(current_pdf, named_pdf)

            if config.split_method == "page" and config.split_page_ranges:
                job.current_step = "페이지 범위 분할"
                self._notify()
                split_pdf_by_page_ranges(named_pdf, config.split_page_ranges, output_dir)
            elif config.split_method == "size" and config.split_size_mb > 0:
                job.current_step = "크기 기준 분할"
                self._notify()
                split_pdf_by_size(named_pdf, config.split_size_mb, output_dir)
        else:
            final_path = output_dir / f"{final_stem}.pdf"
            self._copy_with_retry(current_pdf, final_path)

    # ── Flow 1: 일반+OCR ─────────────────────────────────────

    def _flow_standard_ocr(self, job: Job, tmp: Path, current_pdf: Path) -> Path:
        """일반+OCR: 분할 → ABBYY OCR → 합치기"""
        config = job.config
        ocr_dir = tmp / "ocr_splits"
        ocr_dir.mkdir(parents=True, exist_ok=True)

        job.current_step = "OCR 분할"
        self._notify()
        split_files = split_pdf_by_count(current_pdf, SPLIT_PAGES, ocr_dir)

        if len(split_files) == 1 and split_files[0] == current_pdf:
            dest = ocr_dir / f"{job.book_name}.pdf"
            shutil.copy2(current_pdf, dest)
            split_files = [dest]

        ocr_files = []
        for i, split_file in enumerate(split_files, 1):
            job.current_step = f"OCR 처리중 ({i}/{len(split_files)})"
            self._notify()
            ocr_out = ocr_dir / f"{split_file.stem}_OCR.pdf"
            run_ocr(split_file, ocr_out, config.ocr_language)
            ocr_files.append(ocr_out)

        job.current_step = "OCR 결과 합치기"
        self._notify()
        merged = tmp / f"{job.book_name}.pdf"
        merge_pdfs(ocr_files, merged)
        return merged

    # ── Flow 2: 고급만 (no OCR) ──────────────────────────────

    def _flow_advanced_only(self, job: Job, tmp: Path, current_pdf: Path) -> Path:
        """고급만: 분할 → 첫페이지복사 → ABBYY 레벨 → 첫페이지삭제 → 합치기"""
        config = job.config
        split_dir = tmp / "adv_splits"
        split_dir.mkdir(parents=True, exist_ok=True)

        job.current_step = "분할"
        self._notify()
        split_files = split_pdf_by_count(current_pdf, SPLIT_PAGES, split_dir)

        if len(split_files) == 1 and split_files[0] == current_pdf:
            dest = split_dir / f"{job.book_name}.pdf"
            shutil.copy2(current_pdf, dest)
            split_files = [dest]

        result_files = []
        for i, split_file in enumerate(split_files, 1):
            job.current_step = f"레벨 조정 ({i}/{len(split_files)})"
            self._notify()

            prepended = split_dir / f"{split_file.stem}_prep.pdf"
            prepend_first_page(split_file, prepended)

            leveled = split_dir / f"{split_file.stem}_lev.pdf"
            run_levels_only(prepended, leveled, config.black_point, config.white_point)

            final = split_dir / f"{split_file.stem}_final.pdf"
            delete_first_page(leveled, final)
            result_files.append(final)

        job.current_step = "합치기"
        self._notify()
        merged = tmp / f"{job.book_name}.pdf"
        merge_pdfs(result_files, merged)
        return merged

    # ── Flow 3: 고급+OCR ─────────────────────────────────────

    def _flow_advanced_ocr(self, job: Job, tmp: Path, current_pdf: Path) -> Path:
        """고급+OCR: 분할 → ABBYY 레벨+OCR → 합치기"""
        config = job.config
        split_dir = tmp / "adv_ocr_splits"
        split_dir.mkdir(parents=True, exist_ok=True)

        job.current_step = "분할"
        self._notify()
        split_files = split_pdf_by_count(current_pdf, SPLIT_PAGES, split_dir)

        if len(split_files) == 1 and split_files[0] == current_pdf:
            dest = split_dir / f"{job.book_name}.pdf"
            shutil.copy2(current_pdf, dest)
            split_files = [dest]

        result_files = []
        for i, split_file in enumerate(split_files, 1):
            job.current_step = f"레벨+OCR ({i}/{len(split_files)})"
            self._notify()
            out = split_dir / f"{split_file.stem}_done.pdf"
            run_levels_with_ocr(split_file, out, config.black_point, config.white_point, config.ocr_language)
            result_files.append(out)

        job.current_step = "합치기"
        self._notify()
        merged = tmp / f"{job.book_name}.pdf"
        merge_pdfs(result_files, merged)
        return merged

    def _copy_with_retry(self, src: Path, dst: Path, max_retries: int = 3, delay: int = 5):
        """파일 복사 (실패 시 재시도)"""
        import time
        for attempt in range(1, max_retries + 1):
            try:
                shutil.copy2(src, dst)
                return
            except OSError as e:
                if attempt < max_retries:
                    logger.warning(f"파일 복사 실패 (시도 {attempt}/{max_retries}): {e} - {delay}초 후 재시도")
                    time.sleep(delay)
                else:
                    raise

    def _should_zip_customer(self, customer_name: str, expected_count: int | None) -> bool:
        """출력폴더/고객명/ 안의 책 서브폴더 수가 expected_count 이상이면 True"""
        if not expected_count or expected_count <= 0:
            return False
        customer_dir = self.output_folder / customer_name
        if not customer_dir.exists():
            return False
        book_count = sum(1 for d in customer_dir.iterdir() if d.is_dir())
        return book_count >= expected_count

    def _create_zip(self, customer_name: str):
        """고객의 모든 완료된 책을 ZIP으로 압축 후 폴더 삭제"""
        customer_dir = self.output_folder / customer_name
        if not customer_dir.exists():
            return

        zip_paths = create_customer_zip(customer_name, customer_dir, self.output_folder)
        for zp in zip_paths:
            logger.info(f"ZIP 생성: {zp.name}")

        if zip_paths:
            # ZIP 생성 후 고객 폴더 삭제 (ZIP만 남김)
            shutil.rmtree(customer_dir, ignore_errors=True)
