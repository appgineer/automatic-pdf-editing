"""파이프라인 실행"""

import gc
import logging
import shutil
import threading
import tempfile
from pathlib import Path

from automation.models import Job, JobStatus
from automation.queue_manager import QueueManager
from automation.pipeline.merge import merge_pdfs, count_pages
from automation.pipeline.split import split_pdf_by_count, split_pdf_by_page_ranges, split_pdf_by_size
from automation.pipeline.abbyy_editor import run_levels_only, run_levels_with_ocr, run_ocr_only
from automation.pipeline.page_utils import prepend_first_page, delete_first_page
from automation.pipeline.recompress import compress_pdf
from automation.pipeline.compress import create_customer_zip

logger = logging.getLogger(__name__)

SPLIT_PAGES = 300  # 분할 단위 (OCR, 고급 공통)
ABBYY_ATTEMPTS = 2  # 페이지 수 불일치 시 조각 재처리 포함 총 시도 횟수


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

    def _step(self, job: Job, text: str):
        """진행 단계 표시 (PDF 여러 개면 '[2/3] ' 접두사가 붙는다)"""
        job.current_step = f"{job.part_label}{text}"
        self._notify()

    def _abbyy_chunk(self, label: str, expected: int, produce) -> Path:
        """produce(tag)로 조각을 처리하고 페이지 수를 검증. 불일치면 재시도.

        ABBYY는 완료 판정이 '파일 크기가 안 변하면 끝'이라 페이지가 빠진 채로
        저장돼도 통과한다. 조각마다 페이지 수를 세어 누락을 잡는다.

        produce는 tag를 파일명에 섞어 매 시도마다 새 경로에 쓴다. 같은 경로에
        다시 저장하면 ABBYY 덮어쓰기 대화상자에 걸리고, _wait_for_file_complete()가
        이전 파일을 보고 즉시 '완료'로 판정해버린다.
        """
        actual = -1
        for attempt in range(1, ABBYY_ATTEMPTS + 1):
            out = produce("" if attempt == 1 else f"_r{attempt}")
            actual = count_pages(out)
            if actual == expected:
                return out
            logger.error(
                f"{label}: 페이지 수 불일치 (입력 {expected}p → 출력 {actual}p) "
                f"— 시도 {attempt}/{ABBYY_ATTEMPTS}"
            )
        raise RuntimeError(
            f"{label}: ABBYY 처리 중 페이지 누락 — 입력 {expected}p, "
            f"마지막 출력 {actual}p ({ABBYY_ATTEMPTS}회 시도 실패)"
        )

    def _verify_merged(self, job: Job, source: Path, merged: Path):
        """조각을 다시 합친 결과가 원본과 같은 페이지 수인지 확인"""
        expected = count_pages(source)
        actual = count_pages(merged)
        if actual != expected:
            raise RuntimeError(
                f"{job.book_name}: 조각 합치기 후 페이지 수 불일치 "
                f"(원본 {expected}p → 결과 {actual}p)"
            )

    def _run_loop(self):
        import time
        while self._running:
            job = self.queue.get_next_job()
            if job:
                self._process_job(job)
            else:
                time.sleep(1)

    def _compute_final_stem(self, job: Job) -> str:
        suffix = ""
        if job.config.scan_type == "고급":
            suffix += "_고급"
        if job.config.ocr:
            suffix += "_OCR"
        return f"{job.book_name}{suffix}"

    def _is_job_done(self, job: Job) -> bool:
        """출력물이 이미 존재하면 True (재개용)"""
        for zp in self.output_folder.glob(f"{job.customer_name}님*.zip"):
            if zp.is_file():
                return True

        customer_dir = self.output_folder / job.customer_name
        final_stem = self._compute_final_stem(job)

        # 단일 평탄 파일
        flat = customer_dir / f"{final_stem}.pdf"
        if flat.exists() and flat.stat().st_size > 0:
            return True

        # 여러 파일로 쪼개져 책 폴더로 묶인 경우
        book_dir = customer_dir / job.book_name
        if book_dir.is_dir():
            return any(p.stat().st_size > 0 for p in book_dir.glob("*.pdf"))

        return False

    def _process_job(self, job: Job):
        if self._is_job_done(job):
            job.status = JobStatus.DONE
            job.current_step = "이미 완료됨 (건너뜀)"
            logger.info(f"이미 완료된 작업 건너뜀: {job.display_name}")
            self._notify()
            if self._should_zip_customer(job.customer_name, job.expected_count):
                self._create_zip(job.customer_name)
            return

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

    def _process_pdf(self, job: Job, tmp: Path, src_pdf: Path) -> Path:
        """PDF 한 개를 Flow + 이미지 재압축까지 처리하고 결과 경로 반환"""
        config = job.config
        current_pdf = src_pdf

        # --- 3가지 Flow 분기 ---
        if config.scan_type == "고급" and config.ocr:
            current_pdf = self._flow_advanced_ocr(job, tmp, current_pdf)
        elif config.scan_type == "고급":
            current_pdf = self._flow_advanced_only(job, tmp, current_pdf)
        elif config.ocr:
            current_pdf = self._flow_standard_ocr(job, tmp, current_pdf)

        # --- 이미지 재압축: JPEG2000→JPEG 코덱 변환 (고급 모드만, 아이패드 렉 방지) ---
        if config.scan_type == "고급":
            self._step(job, "이미지 재압축")
            compressed = tmp / f"{job.book_name}_recomp.pdf"
            if compress_pdf(current_pdf, compressed):
                current_pdf = compressed
            else:
                logger.warning(f"이미지 재압축 실패 — 원본 사용: {job.book_name}")

        return current_pdf

    def _run_pipeline(self, job: Job, tmp: Path):
        pdf_files = job.get_pdf_files()
        config = job.config

        if len(pdf_files) == 1:
            current_pdf = self._process_pdf(job, tmp, pdf_files[0])
        else:
            # PDF 여러 개: 각각 따로 처리(재압축까지) 후 파일명 순서대로 병합
            expected_pages = sum(count_pages(p) for p in pdf_files)
            logger.info(
                f"PDF {len(pdf_files)}개 개별 처리 (병합 순서): "
                f"{[p.name for p in pdf_files]} — 총 {expected_pages}p"
            )

            processed = []
            try:
                for i, src in enumerate(pdf_files, 1):
                    job.part_label = f"[{i}/{len(pdf_files)}] "
                    part_tmp = tmp / f"part{i:02d}"
                    part_tmp.mkdir(parents=True, exist_ok=True)

                    result = self._process_pdf(job, part_tmp, src)

                    # 결과만 밖으로 빼고 조각 작업물은 즉시 정리 (임시 디스크 절약).
                    # Flow도 재압축도 안 도는 설정(일반+OCR없음)이면 result가 입력폴더의
                    # 원본이므로 옮기면 안 된다 — 그 경우만 복사한다.
                    kept = tmp / f"processed_{i:02d}.pdf"
                    if result == src:
                        shutil.copy2(str(result), str(kept))
                    else:
                        shutil.move(str(result), str(kept))
                    shutil.rmtree(part_tmp, ignore_errors=True)
                    processed.append(kept)
            finally:
                job.part_label = ""

            self._step(job, "PDF 합치기")
            merged = tmp / f"{job.book_name}_merged.pdf"
            merge_pdfs(processed, merged)

            actual = count_pages(merged)
            if actual != expected_pages:
                raise RuntimeError(
                    f"최종 페이지 수 불일치: 입력 합계 {expected_pages}p → 결과 {actual}p "
                    f"— 페이지가 누락되어 출력하지 않습니다"
                )
            logger.info(f"병합 완료: PDF {len(pdf_files)}개 → {actual}p")
            current_pdf = merged

        # --- 파일명 접미사 조합 ---
        final_stem = self._compute_final_stem(job)

        # --- 최종 출력 (출력폴더/고객명/) ---
        output_dir = self.output_folder / job.customer_name
        output_dir.mkdir(parents=True, exist_ok=True)

        if config.is_split and (config.split_method == "page" or config.split_method == "size"):
            # 분할 함수가 stem 기반으로 파일명을 만들므로 접미사 포함된 이름으로 복사
            named_pdf = tmp / f"{final_stem}.pdf"
            shutil.copy2(current_pdf, named_pdf)

            split_tmp = tmp / "split_out"
            split_tmp.mkdir(parents=True, exist_ok=True)
            parts = []
            if config.split_method == "page" and config.split_page_ranges:
                job.current_step = "페이지 범위 분할"
                self._notify()
                parts = split_pdf_by_page_ranges(named_pdf, config.split_page_ranges, split_tmp)
            elif config.split_method == "size" and config.split_size_mb > 0:
                job.current_step = "크기 기준 분할"
                self._notify()
                parts = split_pdf_by_size(named_pdf, config.split_size_mb, split_tmp)

            if len(parts) >= 2:
                # 여러 파일로 쪼개진 책만 자기 폴더로 묶음
                book_dir = output_dir / job.book_name
                book_dir.mkdir(parents=True, exist_ok=True)
                for part in parts:
                    dest = book_dir / part.name
                    if dest.exists():
                        raise FileExistsError(
                            f"출력 파일명 충돌: '{book_dir.name}/{dest.name}'"
                        )
                    shutil.move(str(part), str(dest))
            elif len(parts) == 1:
                # 결과가 1개면 평탄하게 (이름 정규화)
                dest = output_dir / f"{final_stem}.pdf"
                if dest.exists():
                    raise FileExistsError(
                        f"출력 파일명 충돌: '{dest.name}' — 다른 책과 이름이 겹칩니다. 책 폴더명을 바꿔주세요."
                    )
                shutil.move(str(parts[0]), str(dest))
        else:
            final_path = output_dir / f"{final_stem}.pdf"
            if final_path.exists():
                raise FileExistsError(
                    f"출력 파일명 충돌: '{final_path.name}' — 다른 책과 이름이 겹칩니다. 책 폴더명을 바꿔주세요."
                )
            self._copy_with_retry(current_pdf, final_path)

    # ── Flow 1: 일반+OCR ─────────────────────────────────────

    def _flow_standard_ocr(self, job: Job, tmp: Path, current_pdf: Path) -> Path:
        """일반+OCR: 분할 → ABBYY OCR → 합치기"""
        config = job.config
        ocr_dir = tmp / "ocr_splits"
        ocr_dir.mkdir(parents=True, exist_ok=True)

        self._step(job, "OCR 분할")
        split_files = split_pdf_by_count(current_pdf, SPLIT_PAGES, ocr_dir)

        if len(split_files) == 1 and split_files[0] == current_pdf:
            dest = ocr_dir / f"{job.book_name}.pdf"
            shutil.copy2(current_pdf, dest)
            split_files = [dest]

        ocr_files = []
        for i, split_file in enumerate(split_files, 1):
            self._step(job, f"OCR 처리중 ({i}/{len(split_files)})")

            def produce(tag, split_file=split_file):
                out = ocr_dir / f"{split_file.stem}{tag}_OCR.pdf"
                run_ocr_only(split_file, out, config.ocr_language)
                return out

            ocr_files.append(self._abbyy_chunk(
                f"{job.book_name} 조각 {i}/{len(split_files)}",
                count_pages(split_file), produce))

        self._step(job, "OCR 결과 합치기")
        merged = tmp / f"{job.book_name}.pdf"
        merge_pdfs(ocr_files, merged)
        self._verify_merged(job, current_pdf, merged)
        return merged

    # ── Flow 2: 고급만 (no OCR) ──────────────────────────────

    def _flow_advanced_only(self, job: Job, tmp: Path, current_pdf: Path) -> Path:
        """고급만: 분할 → 첫페이지복사 → ABBYY 레벨 → 첫페이지삭제 → 합치기"""
        config = job.config
        split_dir = tmp / "adv_splits"
        split_dir.mkdir(parents=True, exist_ok=True)

        self._step(job, "분할")
        split_files = split_pdf_by_count(current_pdf, SPLIT_PAGES, split_dir)

        if len(split_files) == 1 and split_files[0] == current_pdf:
            dest = split_dir / f"{job.book_name}.pdf"
            shutil.copy2(current_pdf, dest)
            split_files = [dest]

        result_files = []
        for i, split_file in enumerate(split_files, 1):
            self._step(job, f"레벨 조정 ({i}/{len(split_files)})")

            def produce(tag, split_file=split_file):
                prepended = split_dir / f"{split_file.stem}{tag}_prep.pdf"
                prepend_first_page(split_file, prepended)

                leveled = split_dir / f"{split_file.stem}{tag}_lev.pdf"
                run_levels_only(prepended, leveled, config.black_point, config.white_point)

                final = split_dir / f"{split_file.stem}{tag}_final.pdf"
                delete_first_page(leveled, final)
                return final

            result_files.append(self._abbyy_chunk(
                f"{job.book_name} 조각 {i}/{len(split_files)}",
                count_pages(split_file), produce))

        self._step(job, "합치기")
        merged = tmp / f"{job.book_name}.pdf"
        merge_pdfs(result_files, merged)
        self._verify_merged(job, current_pdf, merged)
        return merged

    # ── Flow 3: 고급+OCR ─────────────────────────────────────

    def _flow_advanced_ocr(self, job: Job, tmp: Path, current_pdf: Path) -> Path:
        """고급+OCR: 분할 → ABBYY 레벨+OCR → 합치기"""
        config = job.config
        split_dir = tmp / "adv_ocr_splits"
        split_dir.mkdir(parents=True, exist_ok=True)

        self._step(job, "분할")
        split_files = split_pdf_by_count(current_pdf, SPLIT_PAGES, split_dir)

        if len(split_files) == 1 and split_files[0] == current_pdf:
            dest = split_dir / f"{job.book_name}.pdf"
            shutil.copy2(current_pdf, dest)
            split_files = [dest]

        result_files = []
        for i, split_file in enumerate(split_files, 1):
            self._step(job, f"레벨+OCR ({i}/{len(split_files)})")

            def produce(tag, split_file=split_file):
                out = split_dir / f"{split_file.stem}{tag}_done.pdf"
                run_levels_with_ocr(split_file, out, config.black_point,
                                    config.white_point, config.ocr_language)
                return out

            result_files.append(self._abbyy_chunk(
                f"{job.book_name} 조각 {i}/{len(split_files)}",
                count_pages(split_file), produce))

        self._step(job, "합치기")
        merged = tmp / f"{job.book_name}.pdf"
        merge_pdfs(result_files, merged)
        self._verify_merged(job, current_pdf, merged)
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
        """고객의 완료(DONE) 작업 수가 expected_count 이상이면 True"""
        if not expected_count or expected_count <= 0:
            return False
        done = sum(
            1 for j in self.queue.jobs
            if j.customer_name == customer_name and j.status == JobStatus.DONE
        )
        return done >= expected_count

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
