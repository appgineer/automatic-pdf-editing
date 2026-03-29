"""메인 윈도우"""

import os
import tkinter as tk
from pathlib import Path

from automation.config import load_settings, save_settings
from automation.queue_manager import QueueManager
from automation.watcher import FolderWatcher
from automation.pipeline.runner import PipelineRunner
from automation.gui.job_tree import JobTree
from automation.gui.controls import FolderSelector, ActionButtons


class MainWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("PDF 자동 처리 시스템")
        self.root.geometry("750x650")

        self.queue = QueueManager()
        self.runner: PipelineRunner | None = None
        self.watcher = FolderWatcher(self.queue, on_new_job=self._on_new_job)

        self._build_ui()
        self._load_settings()
        self._scan_input_folder()
        self._start_auto_scan()

    def _build_ui(self):
        # 폴더 선택
        folder_frame = tk.Frame(self.root, padx=8, pady=8)
        folder_frame.pack(fill=tk.X)

        self.input_selector = FolderSelector(folder_frame, "작업예정:", on_change=self._on_folder_change)
        self.input_selector.pack(fill=tk.X, pady=2)

        self.output_selector = FolderSelector(folder_frame, "완료파일:", on_change=self._on_folder_change)
        self.output_selector.pack(fill=tk.X, pady=2)

        # 액션 버튼
        self.actions = ActionButtons(
            folder_frame,
            on_start=self._on_start,
            on_stop=self._on_stop,
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

    def _start_auto_scan(self):
        """시작 전 5초마다 자동 스캔"""
        self._auto_scan_id = self.root.after(5000, self._auto_scan_tick)

    def _stop_auto_scan(self):
        """자동 스캔 중지"""
        if hasattr(self, '_auto_scan_id') and self._auto_scan_id:
            self.root.after_cancel(self._auto_scan_id)
            self._auto_scan_id = None

    def _auto_scan_tick(self):
        """자동 스캔 1회 실행 후 다음 예약"""
        self._scan_input_folder()
        self._auto_scan_id = self.root.after(5000, self._auto_scan_tick)

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

        # 자동 스캔 중지 (watcher 스레드가 대신 감시)
        self._stop_auto_scan()

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
        self._start_auto_scan()

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
                if self.shutdown_var.get():
                    self._shutdown_computer()
            else:
                self.status_var.set("실행중 - 폴더 감시중...")
        else:
            self.status_var.set("대기중")

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
