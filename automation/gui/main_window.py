"""메인 윈도우"""

import glob
import logging
import os
import shutil
import stat
import subprocess
import tempfile
import tkinter as tk
from pathlib import Path

logger = logging.getLogger(__name__)

from automation.config import load_settings, save_settings
from automation.error_log import setup_error_log
from automation.queue_manager import QueueManager
from automation.watcher import FolderWatcher
from automation.pipeline.runner import PipelineRunner
from automation.pipeline.ocr import _close_abbyy
from automation.gui.job_tree import JobTree
from automation.gui.controls import FolderSelector, ActionButtons


class MainWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("PDF 자동 처리 시스템")
        self.root.geometry("1500x1300")

        self.queue = QueueManager()
        self.runner: PipelineRunner | None = None
        self.watcher = FolderWatcher(self.queue, on_new_job=self._on_new_job)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._load_settings()
        self._scan_input_folder()

    def _build_ui(self):
        # 폴더 선택
        folder_frame = tk.Frame(self.root, padx=8, pady=8)
        folder_frame.pack(fill=tk.X)

        self.input_selector = FolderSelector(folder_frame, "작업예정:",
            on_change=self._on_folder_change)
        self.input_selector.pack(fill=tk.X, pady=2)

        self.output_selector = FolderSelector(folder_frame, "완료파일:",
            on_change=self._on_folder_change)
        self.output_selector.pack(fill=tk.X, pady=2)

        # 액션 버튼
        self.actions = ActionButtons(
            folder_frame,
            on_start=self._on_start,
            on_stop=self._on_stop,
            on_update=self._on_update,
            on_cache_delete=self._on_cache_delete,
            on_up=self._on_move_up,
            on_down=self._on_move_down,
        )
        self.actions.pack(fill=tk.X, pady=4)

        # 구분선
        tk.Frame(self.root, height=1, bg="#cccccc").pack(fill=tk.X)

        # 작업 목록
        self.job_tree = JobTree(self.root)
        self.job_tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # 완료 후 종료 체크박스 (작업 목록 아래, 오른쪽 정렬)
        self.shutdown_var = tk.BooleanVar(value=False)
        self.shutdown_btn = tk.Button(
            self.root, text="☐ 모든 작업 완료 후 컴퓨터 종료",
            font=("", 10), relief=tk.FLAT,
            command=self._toggle_shutdown, bd=0, highlightthickness=0
        )
        self.shutdown_btn.pack(padx=8, anchor=tk.E)

        # 상태바
        self.status_var = tk.StringVar(value="대기중")
        status_bar = tk.Label(
            self.root, textvariable=self.status_var,
            anchor=tk.W, relief=tk.SUNKEN, padx=8, pady=4
        )
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def _toggle_shutdown(self):
        self.shutdown_var.set(not self.shutdown_var.get())
        if self.shutdown_var.get():
            self.shutdown_btn.config(text="☑ 모든 작업 완료 후 컴퓨터 종료")
        else:
            self.shutdown_btn.config(text="☐ 모든 작업 완료 후 컴퓨터 종료")

    def _load_settings(self):
        settings = load_settings()
        if settings["input_folder"]:
            self.input_selector.set_path(settings["input_folder"])
        if settings["output_folder"]:
            self.output_selector.set_path(settings["output_folder"])

    def _save_settings(self):
        save_settings({
            "input_folder": self.input_selector.get_path(),
            "output_folder": self.output_selector.get_path(),
        })

    def _on_folder_change(self, _path: str):
        self._save_settings()
        self._scan_input_folder()

    def _scan_input_folder(self):
        """입력폴더를 스캔하여 리스트만 불러오기 (작업 시작 안 함)"""
        input_path = self.input_selector.get_path()
        if not input_path:
            return
        input_dir = Path(input_path)
        if not input_dir.exists():
            return
        self.watcher.scan_once(input_dir)
        self._refresh_tree()

    def _on_start(self):
        input_path = self.input_selector.get_path()
        output_path = self.output_selector.get_path()

        if not input_path or not output_path:
            self.status_var.set("작업예정/완료파일 폴더를 선택해주세요")
            return

        input_dir = Path(input_path)
        output_dir = Path(output_path)

        if not input_dir.exists():
            self.status_var.set("작업예정 폴더가 존재하지 않습니다")
            return

        output_dir.mkdir(parents=True, exist_ok=True)
        setup_error_log(output_dir)

        # 감시 시작 (새 폴더 추가 감지용)
        self.watcher.start(input_dir)

        # 파이프라인 시작
        self.runner = PipelineRunner(self.queue, output_dir, on_update=self._on_job_update)
        self.runner.start()

        self.actions.set_running(True)
        self.status_var.set("실행중 - 폴더 감시중...")
        self._save_settings()

    def _on_stop(self):
        if self.watcher:
            self.watcher.stop()
        if self.runner:
            self.runner.stop()

        self.actions.set_running(False)
        self.status_var.set("중지됨")

    def _on_close(self):
        """X 버튼 종료: ABBYY 종료 → 임시폴더 정리 → 즉시 종료"""
        # 1. ABBYY 프로세스 종료 (파일 잠금 해제)
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/IM", "FineReaderOCR.exe"],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass

        # 2. 파이프라인 플래그만 끄기 (스레드 대기 안 함)
        if self.runner:
            self.runner._running = False
        if self.watcher:
            self.watcher.stop()

        # 3. 남은 임시폴더 정리
        tmp_base = tempfile.gettempdir()
        for d in glob.glob(os.path.join(tmp_base, "tmp*")):
            if os.path.isdir(d):
                try:
                    shutil.rmtree(d)
                except Exception:
                    pass

        logger.info("앱 종료 - 정리 완료")
        self.root.destroy()

    def _on_new_job(self, job):
        """새 작업 감지 시 (감시 스레드에서 호출)"""
        self.root.after(0, self._refresh_tree)

    def _on_job_update(self):
        """작업 상태 변경 시 (작업 스레드에서 호출)"""
        self.root.after(0, self._refresh_tree)

    def _refresh_tree(self):
        jobs = self.queue.jobs
        self.job_tree.refresh(jobs)

        # 상태바 업데이트: 현재 작업중인 항목 표시
        for job in jobs:
            if job.status.value == "작업중":
                self.status_var.set(f"현재: {job.book_name} - {job.current_step}")
                return

        if self.runner and self.runner._running:
            # 모든 작업 완료 체크
            if jobs and all(j.status.value in ("완료", "오류") for j in jobs):
                self.status_var.set("모든 작업 완료")
                self._update_error_summary()
                if self.shutdown_var.get():
                    self._shutdown_computer()
            else:
                self.status_var.set("실행중 - 폴더 감시중...")
        else:
            self.status_var.set("대기중")

    def _update_error_summary(self):
        """배치 종료 시 에러난 책을 출력폴더의 에러요약.txt로 남김(에러 없으면 기존 요약 삭제)."""
        if not self.runner:
            return
        summary_path = self.runner.output_folder / "에러요약.txt"
        errored = [j for j in self.queue.jobs if j.status.value == "오류"]
        if not errored:
            if summary_path.exists():
                try:
                    summary_path.unlink()
                except Exception:
                    pass
            return

        from datetime import datetime
        lines = [
            f"에러 요약  ({datetime.now():%Y-%m-%d %H:%M:%S})",
            f"실패한 책: {len(errored)}개",
            "",
        ]
        for j in errored:
            lines.append(f"- {j.display_name}")
            if j.error_message:
                lines.append(f"    이유: {j.error_message}")
        lines += ["", "※ 위 책들은 압축되지 않았습니다. 프로그램을 다시 실행하면 자동으로 다시 시도합니다."]
        try:
            summary_path.write_text("\n".join(lines), encoding="utf-8")
        except Exception as e:
            logger.warning(f"에러요약 작성 실패: {e}")

    def _shutdown_computer(self):
        """컴퓨터 전원 끄기 (취소 가능, 시스템 알림 없음)"""
        self._shutdown_cancelled = False
        self._shutdown_remaining = 60
        self.status_var.set("60초 후 컴퓨터를 종료합니다...")

        # 취소 버튼 팝업 (메인 창 가운데에 표시)
        self._shutdown_popup = tk.Toplevel(self.root)
        self._shutdown_popup.title("컴퓨터 종료")
        self._shutdown_popup.attributes("-topmost", True)
        self._shutdown_popup.protocol("WM_DELETE_WINDOW", lambda: None)
        self._shutdown_popup.resizable(False, False)

        popup_w, popup_h = 500, 200
        root_x = self.root.winfo_x()
        root_y = self.root.winfo_y()
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()
        x = root_x + (root_w - popup_w) // 2
        y = root_y + (root_h - popup_h) // 2
        self._shutdown_popup.geometry(f"{popup_w}x{popup_h}+{x}+{y}")

        self._shutdown_label = tk.Label(
            self._shutdown_popup, text="60초 후 컴퓨터가 종료됩니다.", font=("", 12)
        )
        self._shutdown_label.pack(padx=30, pady=(30, 15))
        tk.Button(
            self._shutdown_popup, text="종료 취소", font=("", 12), width=12,
            command=self._cancel_shutdown
        ).pack(pady=(5, 25))

        self._shutdown_tick()

    def _shutdown_tick(self):
        """1초마다 카운트다운, 0이 되면 즉시 종료"""
        if self._shutdown_cancelled:
            return
        self._shutdown_remaining -= 1
        if self._shutdown_remaining <= 0:
            self._shutdown_popup.destroy()
            os.system("shutdown /s /f /t 0")
            return
        self._shutdown_label.config(text=f"{self._shutdown_remaining}초 후 컴퓨터가 종료됩니다.")
        self.status_var.set(f"{self._shutdown_remaining}초 후 컴퓨터를 종료합니다...")
        self.root.after(1000, self._shutdown_tick)

    def _cancel_shutdown(self):
        self._shutdown_cancelled = True
        self.status_var.set("컴퓨터 종료가 취소되었습니다.")
        self._shutdown_popup.destroy()

    def _on_move_up(self):
        customer = self.job_tree.get_selected_customer()
        if customer:
            self.queue.move_customer_up(customer)
            self._refresh_tree()

    def _on_move_down(self):
        customer = self.job_tree.get_selected_customer()
        if customer:
            self.queue.move_customer_down(customer)
            self._refresh_tree()

    def _on_update(self):
        """업데이트 버튼 (기능 미구현 — 추후 정의)"""
        self.status_var.set("업데이트 기능은 준비 중입니다")
        logger.info("업데이트 버튼 클릭 (미구현)")

    def _on_cache_delete(self):
        """ABBYY FineReaderShell 캐시 폴더 내용물 삭제"""
        from tkinter import messagebox

        cache_dir = Path(tempfile.gettempdir()) / "ABBYY" / "FineReader" / "16" / "FineReaderShell"

        if not cache_dir.exists():
            messagebox.showinfo("캐시 삭제", "삭제할 캐시 폴더가 없습니다.")
            self.status_var.set("캐시 폴더 없음")
            return

        # 확인
        if not messagebox.askyesno(
            "캐시 삭제",
            f"ABBYY 캐시를 모두 삭제할까요?\n\n경로: {cache_dir}",
        ):
            return

        # 1. ABBYY 프로세스 종료 + 완전 종료 대기 (파일 잠금 해제)
        #    taskkill만 보내면 비동기라 즉시 삭제 시 파일이 아직 잠겨있음.
        #    _close_abbyy는 tasklist 폴링으로 진짜 종료 확인 + 3초 추가 대기까지 수행.
        self.status_var.set("ABBYY 종료 대기중...")
        self.root.update_idletasks()
        try:
            _close_abbyy(timeout=15)
        except Exception as e:
            logger.warning(f"ABBYY 종료 대기 중 오류: {e}")

        # 2. FineReaderShell 폴더 통째로 삭제
        #    ABBYY가 다음 실행 시 자동 재생성하므로 빈 폴더 남길 필요 없음.
        #    설정/옵션은 AppData\Roaming\ABBYY에 별도 보관되어 있어 영향 없음.
        self.status_var.set("캐시 폴더 삭제중...")
        self.root.update_idletasks()

        def _on_rm_error(func, path, _exc):
            # 읽기전용 속성 때문에 WinError 5(액세스 거부)가 나는 경우:
            # 쓰기 가능으로 바꾼 뒤 재시도.
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except Exception:
                pass

        try:
            shutil.rmtree(cache_dir, onerror=_on_rm_error)
        except Exception as e:
            logger.warning(f"캐시 삭제 rmtree 예외: {e}")

        if not cache_dir.exists():
            msg = "캐시 삭제 완료 (FineReaderShell 폴더 삭제됨)"
            logger.info(msg)
            self.status_var.set(msg)
            messagebox.showinfo("캐시 삭제", msg)
        else:
            # 읽기전용 해제로도 안 지워지면 진짜 잠긴 파일이 남은 것
            try:
                remaining = [f.name for f in cache_dir.iterdir()]
            except Exception:
                remaining = []
            err_msg = f"캐시 삭제 실패: 일부 파일이 남음 {remaining}"
            logger.error(err_msg)
            self.status_var.set("캐시 삭제 실패 (일부 파일 잠김)")
            messagebox.showwarning(
                "캐시 삭제 실패",
                f"일부 파일을 삭제하지 못했습니다.\n\n남은 항목: {remaining}\n\n"
                f"ABBYY가 아직 떠 있거나 다른 프로세스(탐색기, 백신, 검색 인덱서 등)가 "
                f"파일을 잡고 있을 수 있습니다.\n"
                f"ABBYY를 완전히 종료한 뒤 다시 시도해보세요.",
            )
