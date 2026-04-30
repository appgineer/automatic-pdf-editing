"""PDF 자동 처리 시스템 진입점"""

import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
REQUIREMENTS = PROJECT_DIR / "requirements.txt"


IMPORT_NAME_MAP = {
    "PyMuPDF": "fitz",
    "PyGetWindow": "pygetwindow",
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


def auto_update():
    """프로그램 시작 시 자동 업데이트: git pull + 필요 시 pip install"""
    try:
        # 현재 HEAD 저장 (pull 전후 비교용)
        old_head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_DIR, capture_output=True, text=True
        ).stdout.strip()

        # git pull
        result = subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=PROJECT_DIR, capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0:
            print(f"[업데이트] git pull 실패: {result.stderr.strip()}")
            return

        new_head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_DIR, capture_output=True, text=True
        ).stdout.strip()

        if old_head == new_head:
            print("[업데이트] 최신 상태입니다.")
            return

        print("[업데이트] 코드 업데이트 완료.")

        # requirements.txt 변경 확인
        changed = subprocess.run(
            ["git", "diff", "--name-only", old_head, new_head],
            cwd=PROJECT_DIR, capture_output=True, text=True
        ).stdout

        if "requirements.txt" in changed:
            print("[업데이트] 라이브러리 업데이트 중...")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)],
                cwd=PROJECT_DIR, timeout=120
            )
            print("[업데이트] 라이브러리 업데이트 완료.")

    except FileNotFoundError:
        print("[업데이트] git이 설치되어 있지 않습니다. 업데이트를 건너뜁니다.")
    except subprocess.TimeoutExpired:
        print("[업데이트] 네트워크 타임아웃. 업데이트를 건너뜁니다.")
    except Exception as e:
        print(f"[업데이트] 오류 발생, 건너뜁니다: {e}")


if __name__ == "__main__":
    ensure_dependencies()
    auto_update()

    from automation.app import run
    run()
