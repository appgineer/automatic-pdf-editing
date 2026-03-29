"""작업 목록 트리뷰"""

import tkinter as tk
from tkinter import ttk
from automation.models import Job, JobStatus


STATUS_SYMBOLS = {
    JobStatus.WAITING: "\u25cb",  # ○
    JobStatus.RUNNING: "\u25cf",  # ●
    JobStatus.DONE: "\u25cf",     # ●
    JobStatus.ERROR: "\u2716",    # ✖
}

STATUS_COLORS = {
    JobStatus.WAITING: "#999999",
    JobStatus.RUNNING: "#00aa00",
    JobStatus.DONE: "#0066cc",
    JobStatus.ERROR: "#cc0000",
}


class JobTree(ttk.Frame):
    def __init__(self, parent, on_select=None):
        super().__init__(parent)
        self.on_select = on_select
        self._selected_job: Job | None = None

        style = ttk.Style()
        style.configure("JobTree.Treeview", rowheight=28, font=("", 11))

        self.tree = ttk.Treeview(self, columns=("status",), show="tree", selectmode="browse", style="JobTree.Treeview")
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.column("#0", width=350)
        self.tree.column("status", width=80, anchor=tk.E)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(fill=tk.BOTH, expand=True)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # 고객별 노드 ID 추적
        self._customer_nodes: dict[str, str] = {}
        self._job_nodes: dict[str, Job] = {}

    def refresh(self, jobs: list[Job]):
        """전체 트리 갱신"""
        self.tree.delete(*self.tree.get_children())
        self._customer_nodes.clear()
        self._job_nodes.clear()

        # 고객별 그룹
        customers: dict[str, list[Job]] = {}
        for job in jobs:
            customers.setdefault(job.customer_name, []).append(job)

        for customer_name, customer_jobs in customers.items():
            cid = self.tree.insert("", tk.END, text=f"\u25bc {customer_name}", open=True)
            self._customer_nodes[customer_name] = cid

            for job in customer_jobs:
                symbol = STATUS_SYMBOLS[job.status]
                status_text = job.status.value
                node_id = self.tree.insert(
                    cid, tk.END,
                    text=f"  {symbol} {job.book_name}",
                    values=(status_text,),
                )
                self._job_nodes[node_id] = job

                # 색상 태그
                tag = f"status_{job.status.name}"
                self.tree.tag_configure(tag, foreground=STATUS_COLORS[job.status])
                self.tree.item(node_id, tags=(tag,))

    def _on_tree_select(self, event):
        selection = self.tree.selection()
        if not selection:
            return
        node_id = selection[0]
        job = self._job_nodes.get(node_id)
        if job:
            self._selected_job = job
            if self.on_select:
                self.on_select(job)

    def get_selected_job(self) -> Job | None:
        return self._selected_job
