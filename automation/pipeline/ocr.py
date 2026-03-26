"""ABBYY FineReader 16 OCR 자동화 (pyautogui)

Windows 11 + ABBYY FineReader 16 Standard
단축키 기반으로 OCR 편집기를 통해 PDF를 검색 가능한 PDF로 변환.

흐름:
1. 해당 폴더에서 PDF 파일을 직접 열기 (ABBYY OCR 편집기로 열림)
2. Ctrl+. → OCR 언어 설정
3. F10 → Enter → F → V → S → 검색 가능한 PDF로 저장
4. 같은 폴더에 원본파일명_OCR.pdf 로 저장
"""

import os
import time
import subprocess
import logging
from pathlib import Path

import pyautogui
import pyperclip

logger = logging.getLogger(__name__)

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.3

ABBYY_WINDOW_KEYWORD = "FineReader"

# 폴링 간격 (초)
POLL_INTERVAL = 0.5
# 최대 대기 시간 (초)
DEFAULT_TIMEOUT = 60


# ── 창 감지 유틸리티 ──────────────────────────────────────────

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

    # ABBYY 창이 뜰 때까지 대기
    if not _wait_for_abbyy(timeout=30):
        raise RuntimeError("ABBYY FineReader가 열리지 않습니다")

    # 파일 로딩 안정화 대기
    time.sleep(3)
    _find_abbyy_window()


def _set_language(languages: list[str]):
    """Ctrl+. → OCR 언어 설정"""
    logger.info(f"언어 설정: {languages}")

    pyautogui.hotkey("ctrl", ".")
    time.sleep(1)

    # Tab 3번으로 언어 입력창 이동
    for _ in range(3):
        pyautogui.press("tab")
        time.sleep(0.1)

    # 언어 하나씩 입력 후 Enter
    for lang in languages:
        pyperclip.copy(lang)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.3)
        pyautogui.press("enter")
        time.sleep(0.3)

    # 확인 버튼
    pyautogui.press("enter")
    time.sleep(0.5)


def _save_as_searchable_pdf(pdf_path: Path):
    """F10 → Enter → F → V → S → 같은 폴더에 _OCR 붙여서 저장"""
    output_name = f"{pdf_path.stem}_OCR.pdf"
    logger.info(f"검색 가능한 PDF로 저장: {output_name}")

    # F10 → Enter → F → V → S
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

    # 저장 대화상자 — 이미 원본 폴더 위치에 있음
    # 파일명만 _OCR 붙인 이름으로 변경
    pyperclip.copy(output_name)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(3)

    logger.info("저장 완료")


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
        output_path: 출력 PDF 경로 (사용되지 않음 — 같은 폴더에 _OCR.pdf로 저장)
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

    # 3. 저장 (같은 폴더에 _OCR 붙여서)
    _save_as_searchable_pdf(input_path)

    # 4. 문서 닫기
    _close_document()

    actual_output = input_path.parent / f"{input_path.stem}_OCR.pdf"
    logger.info(f"OCR 완료: {actual_output.name}")
    return actual_output
