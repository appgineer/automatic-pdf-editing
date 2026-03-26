"""ABBYY FineReader 16 OCR 자동화 (pyautogui)

Windows 11 + ABBYY FineReader 16 Standard
단축키 기반으로 OCR 편집기를 통해 PDF를 검색 가능한 PDF로 변환.

흐름:
1. 해당 폴더에서 PDF 파일을 직접 열기 (ABBYY OCR 편집기로 열림)
2. Ctrl+. → OCR 언어 설정
3. F10 → Tab*10 → Enter → 다른 이름으로 저장
4. 출력폴더/사람이름/책이름/파일명_OCR.pdf 로 저장
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


def _save_as_searchable_pdf(output_path: Path):
    """F10 → Tab*10 → Enter → 경로 입력 → 저장

    Args:
        output_path: 전체 저장 경로 (출력폴더/사람이름/책이름/파일명_OCR.pdf)
    """
    logger.info(f"검색 가능한 PDF로 저장: {output_path}")

    # 출력 폴더 생성
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # F10 → 메뉴 열기
    pyautogui.press("f10")
    time.sleep(0.5)

    # Tab 10번 → "다른 이름으로 저장" 까지 이동
    for _ in range(10):
        pyautogui.press("tab")
        time.sleep(0.1)

    # Enter → 저장 대화상자 열기
    pyautogui.press("enter")
    time.sleep(1)

    # 저장 경로 입력 (전체 경로)
    pyperclip.copy(str(output_path))
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.3)

    # 저장
    pyautogui.press("enter")
    time.sleep(3)

    logger.info(f"저장 완료: {output_path}")


def _close_document():
    """현재 문서 닫기"""
    pyautogui.hotkey("ctrl", "w")
    time.sleep(0.5)

    # 저장 여부 묻는 대화상자 → 저장 안 함
    pyautogui.press("tab")
    pyautogui.press("enter")
    time.sleep(0.5)


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

    # 1. 파일 직접 열기 → ABBYY OCR 편집기
    _open_file(input_path)

    # 2. 언어 설정
    _set_language(languages)

    # 3. 다른 이름으로 저장 (출력폴더/사람이름/책이름/파일명_OCR.pdf)
    _save_as_searchable_pdf(output_path)

    # 4. 문서 닫기
    _close_document()

    logger.info(f"OCR 완료: {output_path.name}")
    return output_path
