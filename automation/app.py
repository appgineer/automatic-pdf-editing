"""앱 통합"""

import logging
import tkinter as tk
from automation.gui.main_window import MainWindow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def run():
    root = tk.Tk()
    app = MainWindow(root)
    root.mainloop()
