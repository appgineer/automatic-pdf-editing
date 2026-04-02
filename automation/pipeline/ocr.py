"""ABBYY FineReader 16 OCR 자동화 (pyautogui)

Windows 11 + ABBYY FineReader 16 Standard
단축키 기반으로 OCR 편집기를 통해 PDF를 검색 가능한 PDF로 변환.

흐름:
1. 해당 폴더에서 PDF 파일을 직접 열기 (ABBYY OCR 편집기로 열림)
2. Ctrl+. → OCR 언어 설정
3. F10 → Enter → F → V → S → 다른 이름으로 저장
4. Alt+D로 출력폴더/사람이름/책이름/ 경로 입력 → 파일명_OCR.pdf 저장
"""

import os
import time
import logging
from pathlib import Path

import pyautogui
import pyperclip

logger = logging.getLogger(__name__)

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.3

ABBYY_WINDOW_KEYWORD = "FineReader"

POLL_INTERVAL = 0.5
DEFAULT_TIMEOUT = 60


# ── 창 감지 ──────────────────────────────────────────────────

def _find_abbyy_window():
    """ABBYY FineReader 창을 찾아서 활성화"""
    try:
        import pygetwindow as gw
        for win in gw.getAllWindows():
            if ABBYY_WINDOW_KEYWORD.lower() in win.title.lower():
                logger.info(f"ABBYY 창 발견: '{win.title}'")
                if win.isMinimized:
                    win.restore()
                    time.sleep(0.5)
                win.activate()
                time.sleep(0.5)
                try:
                    pyautogui.click(win.left + win.width // 2, win.top + 15)
                    time.sleep(0.3)
                except Exception:
                    pass
                return True
    except Exception as e:
        logger.warning(f"창 찾기 실패: {e}")
    return False


def _wait_for_abbyy(timeout: int = DEFAULT_TIMEOUT) -> bool:
    """ABBYY 창이 나타날 때까지 폴링"""
    start = time.time()
    while time.time() - start < timeout:
        if _find_abbyy_window():
            return True
        time.sleep(POLL_INTERVAL)
    return False


# ── ABBYY 제어 ──────────────────────────────────────────────

def _open_file(pdf_path: Path):
    """PDF 파일을 직접 열어서 ABBYY OCR 편집기로 실행"""
    logger.info(f"파일 열기: {pdf_path}")
    os.startfile(str(pdf_path))

    if not _wait_for_abbyy(timeout=30):
        raise RuntimeError("ABBYY FineReader가 열리지 않습니다")

    time.sleep(3)
    _find_abbyy_window()


def _set_language(languages: list[str]):
    """Ctrl+. → OCR 언어 설정"""
    logger.info(f"언어 설정: {languages}")

    pyautogui.hotkey("ctrl", ".")
    time.sleep(1)

    for _ in range(3):
        pyautogui.press("tab")
        time.sleep(0.1)

    for lang in languages:
        pyperclip.copy(lang)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.3)
        pyautogui.press("enter")
        time.sleep(0.3)

    pyautogui.press("enter")
    time.sleep(0.5)


def _wait_for_file_complete(file_path: Path, timeout: int = 600):
    """파일이 생성되고 크기가 안정될 때까지 대기 (OCR 완료 감지)

    파일 크기가 3초간 변하지 않으면 완료로 판단.
    최대 10분 대기.
    """
    start = time.time()

    # 1. 파일이 생성될 때까지 대기
    while time.time() - start < timeout:
        if file_path.exists() and file_path.stat().st_size > 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError(f"OCR 파일 생성 타임아웃 ({timeout}초): {file_path}")

    # 2. 파일 크기가 안정될 때까지 대기 (3초간 변화 없으면 완료)
    prev_size = -1
    stable_count = 0
    while time.time() - start < timeout:
        current_size = file_path.stat().st_size
        if current_size == prev_size:
            stable_count += 1
            if stable_count >= 3:
                logger.info(f"OCR 저장 완료 ({time.time() - start:.0f}초, {current_size / 1024:.0f}KB)")
                return
        else:
            stable_count = 0
        prev_size = current_size
        time.sleep(1)

    raise RuntimeError(f"OCR 파일 안정화 타임아웃 ({timeout}초): {file_path}")


def _save_as_searchable_pdf(output_path: Path):
    """F10 → Enter → F → V → S → 다른이름으로 저장 → Alt+D로 경로 입력

    Args:
        output_path: 전체 저장 경로 (출력폴더/사람이름/책이름/파일명_OCR.pdf)
    """
    logger.info(f"검색 가능한 PDF로 저장: {output_path}")

    # 출력 폴더 생성
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # F10 → Enter → F → V → S → 다른 이름으로 저장 창 열기
    pyautogui.press("f10")
    time.sleep(0.5)
    pyautogui.press("enter")
    time.sleep(0.3)
    pyautogui.press("f")
    time.sleep(0.3)
    pyautogui.press("v")
    time.sleep(0.3)
    pyautogui.press("s")
    time.sleep(1)

    # 파일명 입력란에 전체 경로를 직접 입력
    # (Windows 저장 대화상자는 전체 경로를 넣으면 해당 폴더에 저장됨)
    pyperclip.copy(str(output_path))
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.3)

    # 저장 (OCR 처리 + 저장이 동시에 진행됨)
    pyautogui.press("enter")

    # OCR + 저장 완료 대기: 파일이 생성되고 크기가 안정될 때까지
    logger.info("OCR 처리 + 저장 대기중...")
    _wait_for_file_complete(output_path)

    logger.info(f"저장 완료: {output_path}")


def _close_abbyy(timeout: int = 15):
    """ABBYY 프로세스 모두 종료 후 완전 종료 확인"""
    import subprocess

    # FineReaderOCR.exe와 FineReader.exe 모두 종료
    for exe in ("FineReaderOCR.exe", "FineReader.exe"):
        try:
            subprocess.run(["taskkill", "/F", "/T", "/IM", exe], capture_output=True)
            logger.info(f"{exe} 종료 명령 실행")
        except Exception as e:
            logger.warning(f"{exe} 종료 실패: {e}")

    # 두 프로세스 모두 완전히 종료될 때까지 폴링
    start = time.time()
    while time.time() - start < timeout:
        still_running = False
        for exe in ("FineReaderOCR.exe", "FineReader.exe"):
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {exe}"],
                capture_output=True, text=True
            )
            if exe in result.stdout:
                still_running = True
                break
        if not still_running:
            logger.info("ABBYY 프로세스 완전 종료 확인")
            time.sleep(3)
            return
        time.sleep(0.5)
    logger.warning("ABBYY 프로세스 종료 타임아웃")


def run_ocr(input_path: Path, output_path: Path, languages: list[str] | str = "Korean") -> Path:
    """ABBYY FineReader 16으로 OCR 실행

    Args:
        input_path: 입력 PDF 경로
        output_path: 출력 PDF 경로 (출력폴더/사람이름/책이름/파일명_OCR.pdf)
        languages: OCR 언어 목록 (예: ["한국어", "영어"])

    Returns:
        출력 PDF 경로
    """
    if isinstance(languages, str):
        languages = [languages]

    logger.info(f"OCR 시작: {input_path.name} (언어: {languages})")

    try:
        # 1. 파일 직접 열기 → ABBYY OCR 편집기
        _open_file(input_path)

        # 2. 언어 설정
        _set_language(languages)

        # 3. 다른 이름으로 저장 (출력폴더/사람이름/책이름/파일명_OCR.pdf)
        _save_as_searchable_pdf(output_path)
    finally:
        # 4. ABBYY 종료 (에러 발생해도 반드시 종료)
        _close_abbyy()

    logger.info(f"OCR 완료: {output_path.name}")
    return output_path
