"""앱 통합"""

import glob
import logging
import os
import shutil
import tempfile
import tkinter as tk
from automation.gui.main_window import MainWindow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

logger = logging.getLogger(__name__)


def _cleanup_temp_folders():
    """이전 실행에서 남은 임시폴더 + ABBYY가 남긴 찌꺼기 파일(xml_file, debug_page) 정리"""
    tmp_base = tempfile.gettempdir()
    for d in glob.glob(os.path.join(tmp_base, "tmp*")):
        if os.path.isdir(d):
            try:
                shutil.rmtree(d)
            except Exception:
                pass
    for pattern in ("xml_file*.xml", "debug_page_*.png"):
        for f in glob.glob(os.path.join(tmp_base, pattern)):
            if os.path.isfile(f):
                try:
                    os.remove(f)
                except Exception:
                    pass
    logger.info("임시폴더 정리 완료")


def run():
    _cleanup_temp_folders()
    root = tk.Tk()
    app = MainWindow(root)
    root.mainloop()
