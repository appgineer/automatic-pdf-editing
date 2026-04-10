"""버튼/폴더 선택 컨트롤"""

import tkinter as tk
from tkinter import filedialog


class FolderSelector(tk.Frame):
    def __init__(self, parent, label_text: str, on_change=None):
        super().__init__(parent)
        self.on_change = on_change

        tk.Label(self, text=label_text, width=8, anchor=tk.W).pack(side=tk.LEFT)

        self.path_var = tk.StringVar()
        self.entry = tk.Entry(self, textvariable=self.path_var, width=40)
        self.entry.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)

        tk.Button(self, text="찾기", command=self._browse).pack(side=tk.LEFT, padx=2)

    def _browse(self):
        folder = self._browse_powershell() or filedialog.askdirectory()
        if folder:
            self.path_var.set(folder)
            if self.on_change:
                self.on_change(folder)

    @staticmethod
    def _browse_powershell() -> str:
        import subprocess
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "Add-Type -AssemblyName System.Windows.Forms; "
                 "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
                 "$f.ShowDialog() | Out-Null; $f.SelectedPath"],
                capture_output=True, text=True, timeout=120
            )
            return result.stdout.strip()
        except Exception:
            return ""

    def get_path(self) -> str:
        return self.path_var.get()

    def set_path(self, path: str):
        self.path_var.set(path)


class ActionButtons(tk.Frame):
    def __init__(self, parent, on_start=None, on_stop=None, on_up=None, on_down=None):
        super().__init__(parent)

        btn_frame = tk.Frame(self)
        btn_frame.pack(fill=tk.X)

        btn_font = ("", 11)

        self.start_btn = tk.Button(btn_frame, text="시작", command=on_start, width=8, font=btn_font, height=1)
        self.start_btn.pack(side=tk.LEFT, padx=4)

        self.stop_btn = tk.Button(btn_frame, text="중지", command=on_stop, width=8, font=btn_font, height=1, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=4)

        tk.Frame(btn_frame, width=20).pack(side=tk.LEFT)

        self.up_btn = tk.Button(btn_frame, text="▲ 위로", command=on_up, width=8, font=btn_font, height=1)
        self.up_btn.pack(side=tk.RIGHT, padx=4)

        self.down_btn = tk.Button(btn_frame, text="▼ 아래로", command=on_down, width=8, font=btn_font, height=1)
        self.down_btn.pack(side=tk.RIGHT, padx=4)

    def set_running(self, running: bool):
        self.start_btn.config(state=tk.DISABLED if running else tk.NORMAL)
        self.stop_btn.config(state=tk.NORMAL if running else tk.DISABLED)
