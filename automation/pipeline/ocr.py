"""ABBYY FineReader 16 OCR 자동화 (pyautogui)

Windows 11 + ABBYY FineReader 16 Standard
단축키 기반으로 OCR 편집기를 통해 PDF를 검색 가능한 PDF로 변환.

흐름:
1. ABBYY FineReader 16 실행
2. Ctrl+R → OCR 편집기 열기 (파일 선택 포함)
3. Ctrl+. → OCR 언어 설정 (Tab*3 → 언어 입력 → Enter)
4. Alt+F → A → S → 검색 가능한 PDF로 저장
"""

import time
import subprocess
import logging
from pathlib import Path

import pyautogui
import pyperclip

logger = logging.getLogger(__name__)

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.3

ABBYY_PATH = r"C:\Program Files\ABBYY FineReader 16\FineReader.exe"

WAIT_LAUNCH = 10  # ABBYY 실행 대기 (초기 로딩이 느림)
WAIT_FILE_OPEN = 5
WAIT_OCR_PER_PAGE = 3
WAIT_SAVE = 5

# ABBYY 창 제목에 포함될 키워드 (부분 일치)
ABBYY_WINDOW_KEYWORD = "FineReader"


def _find_abbyy_window():
    """ABBYY FineReader 창을 찾아서 활성화 (부분 일치)"""
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
                # 제목 표시줄 클릭으로 포커스 잡기 (콘텐츠 영역 클릭 금지)
                try:
                    pyautogui.click(win.left + win.width // 2, win.top + 15)
                    time.sleep(0.3)
                except Exception:
                    pass
                return True
    except Exception as e:
        logger.warning(f"창 찾기 실패: {e}")
    return False


def _launch_abbyy():
    """ABBYY FineReader 16 실행"""
    if _find_abbyy_window():
        logger.info("ABBYY가 이미 실행 중")
        return

    logger.info(f"ABBYY 실행: {ABBYY_PATH}")
    subprocess.Popen(ABBYY_PATH)

    # 최대 20초 대기하며 창이 뜰 때까지 재시도
    for i in range(10):
        time.sleep(2)
        if _find_abbyy_window():
            logger.info(f"ABBYY 실행 완료 ({(i+1)*2}초)")
            return

    raise RuntimeError("ABBYY FineReader를 실행할 수 없습니다")


def _open_in_ocr_editor(pdf_path: Path):
    """Ctrl+R → OCR 편집기 열기 → 파일 선택

    Ctrl+R → Tab*5 → Enter → 경로 붙여넣기 → Enter
    """
    logger.info(f"OCR 편집기로 열기: {pdf_path}")

    # ABBYY 창에 포커스 확인 후 Ctrl+R
    _find_abbyy_window()
    time.sleep(1)
    pyautogui.hotkey("ctrl", "r")
    time.sleep(3)

    # Tab 5번 → Enter로 파일 이름 입력란 활성화
    for _ in range(5):
        pyautogui.press("tab")
        time.sleep(0.1)
    pyautogui.press("enter")
    time.sleep(0.5)

    # 전체 경로 붙여넣기
    pyperclip.copy(str(pdf_path))
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.5)

    # 열기
    pyautogui.press("enter")
    time.sleep(WAIT_FILE_OPEN)


def _set_language(languages: list[str]):
    """Ctrl+. → OCR 언어 설정

    Tab 3번 → 언어 입력창 → 언어 하나씩 입력+Enter → 마지막 Enter로 확인
    """
    logger.info(f"언어 설정: {languages}")
    pyautogui.hotkey("ctrl", ".")
    time.sleep(0.5)

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

    # 마지막 Enter → 확인 버튼
    pyautogui.press("enter")
    time.sleep(0.5)


def _save_as_searchable_pdf(output_path: Path):
    """Alt+F → A → S → 검색 가능한 PDF로 저장"""
    logger.info(f"검색 가능한 PDF로 저장: {output_path}")

    # 출력 폴더가 없으면 생성
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pyautogui.hotkey("alt", "f")
    time.sleep(0.3)
    pyautogui.press("a")
    time.sleep(0.3)
    pyautogui.press("s")
    time.sleep(1)

    # 저장 대화상자에서 경로 입력
    pyperclip.copy(str(output_path))
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.5)
    pyautogui.press("enter")
    time.sleep(WAIT_SAVE)


def _wait_for_ocr_complete(page_count: int = 10):
    """OCR 편집기에서 파일을 열면 자동으로 OCR이 진행됨. 완료 대기."""
    estimated_time = max(WAIT_OCR_PER_PAGE * page_count, 10)
    logger.info(f"OCR 처리 대기 ({estimated_time}초)")
    time.sleep(estimated_time)


def _close_document():
    """현재 문서 닫기"""
    pyautogui.hotkey("ctrl", "w")
    time.sleep(0.5)

    # 저장 여부 묻는 대화상자 → 저장 안 함
    pyautogui.press("tab")
    pyautogui.press("enter")
    time.sleep(0.5)


def _get_page_count(pdf_path: Path) -> int:
    """PDF 페이지 수 확인"""
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        count = doc.page_count
        doc.close()
        return count
    except Exception:
        return 10


def run_ocr(input_path: Path, output_path: Path, languages: list[str] | str = "Korean") -> Path:
    """ABBYY FineReader 16으로 OCR 실행

    Args:
        input_path: 입력 PDF 경로
        output_path: 출력 PDF 경로 (검색 가능한 PDF)
        languages: OCR 언어 목록 (예: ["한국어", "영어"])

    Returns:
        출력 PDF 경로
    """
    if isinstance(languages, str):
        languages = [languages]

    page_count = _get_page_count(input_path)
    logger.info(f"OCR 시작: {input_path.name} ({page_count}페이지, 언어: {languages})")

    # 1. ABBYY 실행/활성화
    _launch_abbyy()

    # 2. Ctrl+R → OCR 편집기로 파일 열기
    _open_in_ocr_editor(input_path)

    # 3. Ctrl+. → 언어 설정
    _set_language(languages)

    # 4. OCR 완료 대기 (편집기가 자동으로 처리)
    _wait_for_ocr_complete(page_count)

    # 5. Alt+F → A → S → 검색 가능한 PDF로 저장
    _save_as_searchable_pdf(output_path)

    # 6. 문서 닫기
    _close_document()

    logger.info(f"OCR 완료: {output_path.name}")
    return output_path
