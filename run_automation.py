"""PDF 자동 처리 시스템 진입점"""

import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
REQUIREMENTS = PROJECT_DIR / "requirements.txt"


IMPORT_NAME_MAP = {
    "PyMuPDF": "fitz",
    "PyGetWindow": "pygetwindow",
    "Pillow": "PIL",
}


def ensure_dependencies():
    """최초 실행 시 requirements.txt 기반으로 미설치 라이브러리 자동 감지 및 설치"""
    missing = False
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        pkg = line.split(">")[0].split("=")[0].strip()
        if not pkg:
            continue
        import_name = IMPORT_NAME_MAP.get(pkg, pkg.lower().replace("-", "_"))
        try:
            __import__(import_name)
        except ImportError:
            missing = True
            break
    if missing:
        print("[초기 설정] 필요한 라이브러리를 설치합니다...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)],
            cwd=PROJECT_DIR, timeout=300
        )
        print("[초기 설정] 라이브러리 설치 완료.")


if __name__ == "__main__":
    ensure_dependencies()

    from automation.app import run
    run()
