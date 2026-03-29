"""메인 윈도우"""

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
        self.root.geometry("550x500")

        self.queue = QueueManager()
        self.runner: PipelineRunner | None = None
        self.watcher = FolderWatcher(self.queue, on_new_job=self._on_new_job)

        self._build_ui()
        self._load_settings()
        self._scan_input_folder()

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

        # 상태바
        self.status_var = tk.StringVar(value="대기중")
        status_bar = tk.Label(
            self.root, textvariable=self.status_var,
            anchor=tk.W, relief=tk.SUNKEN, padx=8, pady=4
        )
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

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
        self.status_var.set("실행중 - 폴더 감시중...")

    def _on_move_up(self):
        job = self.job_tree.get_selected_job()
        if job:
            self.queue.move_up(job)
            self._refresh_tree()

    def _on_move_down(self):
        job = self.job_tree.get_selected_job()
        if job:
            self.queue.move_down(job)
            self._refresh_tree()
