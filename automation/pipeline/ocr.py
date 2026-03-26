"""ABBYY FineReader 16 OCR 자동화 (pyautogui)

Windows 11 + ABBYY FineReader 16 Standard
단축키 기반으로 OCR 편집기를 통해 PDF를 검색 가능한 PDF로 변환.

흐름:
1. ABBYY FineReader 16 실행
2. Ctrl+R → OCR 편집기 열기 (파일 선택 포함)
3. Ctrl+. → OCR 언어 설정 (Tab*3 → 언어 입력 → Enter)
4. F10 → Enter → F → V → S → 검색 가능한 PDF로 저장
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

# ABBYY 창 제목에 포함될 키워드 (부분 일치)
ABBYY_WINDOW_KEYWORD = "FineReader"

# 폴링 간격 (초)
POLL_INTERVAL = 0.5
# 최대 대기 시간 (초)
DEFAULT_TIMEOUT = 60
LONG_TIMEOUT = 300  # OCR 처리 등 오래 걸리는 작업


# ── 창 감지 유틸리티 ──────────────────────────────────────────

def _get_all_windows():
    """현재 열려있는 모든 윈도우 목록 반환"""
    try:
        import pygetwindow as gw
        return gw.getAllWindows()
    except Exception:
        return []


def _find_window(keyword: str):
    """제목에 keyword가 포함된 창을 찾아 반환 (없으면 None)"""
    for win in _get_all_windows():
        if keyword.lower() in win.title.lower():
            return win
    return None


def _wait_for_window(keyword: str, timeout: int = DEFAULT_TIMEOUT) -> bool:
    """keyword가 제목에 포함된 창이 나타날 때까지 대기"""
    logger.debug(f"창 대기: '{keyword}' (최대 {timeout}초)")
    start = time.time()
    while time.time() - start < timeout:
        if _find_window(keyword):
            logger.debug(f"창 발견: '{keyword}' ({time.time() - start:.1f}초)")
            return True
        time.sleep(POLL_INTERVAL)
    logger.warning(f"창 대기 타임아웃: '{keyword}' ({timeout}초)")
    return False


def _wait_for_window_gone(keyword: str, timeout: int = DEFAULT_TIMEOUT) -> bool:
    """keyword가 제목에 포함된 창이 사라질 때까지 대기"""
    logger.debug(f"창 닫힘 대기: '{keyword}' (최대 {timeout}초)")
    start = time.time()
    while time.time() - start < timeout:
        if not _find_window(keyword):
            logger.debug(f"창 닫힘 확인: '{keyword}' ({time.time() - start:.1f}초)")
            return True
        time.sleep(POLL_INTERVAL)
    logger.warning(f"창 닫힘 대기 타임아웃: '{keyword}' ({timeout}초)")
    return False


def _get_window_titles() -> set[str]:
    """현재 열린 모든 창 제목 set 반환"""
    return {win.title for win in _get_all_windows() if win.title.strip()}


def _wait_for_new_window(before_titles: set[str], timeout: int = DEFAULT_TIMEOUT) -> str | None:
    """이전에 없던 새 창이 나타날 때까지 대기. 새 창 제목 반환."""
    logger.debug(f"새 창 대기 (최대 {timeout}초)")
    start = time.time()
    while time.time() - start < timeout:
        current = _get_window_titles()
        new_titles = current - before_titles
        if new_titles:
            title = next(iter(new_titles))
            logger.debug(f"새 창 발견: '{title}' ({time.time() - start:.1f}초)")
            return title
        time.sleep(POLL_INTERVAL)
    logger.warning(f"새 창 대기 타임아웃 ({timeout}초)")
    return None


# ── ABBYY 제어 ──────────────────────────────────────────────

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

    # 창이 뜰 때까지 폴링
    if not _wait_for_window(ABBYY_WINDOW_KEYWORD, timeout=30):
        raise RuntimeError("ABBYY FineReader를 실행할 수 없습니다")

    _find_abbyy_window()
    logger.info("ABBYY 실행 완료")


def _open_in_ocr_editor(pdf_path: Path):
    """Ctrl+R → OCR 편집기 열기 → 파일 선택"""
    logger.info(f"OCR 편집기로 열기: {pdf_path}")

    _find_abbyy_window()
    time.sleep(0.5)

    # 현재 창 목록 스냅샷
    before_titles = _get_window_titles()

    pyautogui.hotkey("ctrl", "r")

    # 파일 선택 대화상자가 열릴 때까지 대기
    _wait_for_new_window(before_titles, timeout=DEFAULT_TIMEOUT)
    time.sleep(0.5)

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

    # 열기 전 창 목록 스냅샷
    before_titles = _get_window_titles()

    # 열기
    pyautogui.press("enter")

    # 파일 열기 대화상자가 닫히고 편집기가 로딩될 때까지 대기
    time.sleep(2)
    logger.info("파일 로딩 대기중...")


def _set_language(languages: list[str]):
    """Ctrl+. → OCR 언어 설정"""
    logger.info(f"언어 설정: {languages}")

    before_titles = _get_window_titles()

    pyautogui.hotkey("ctrl", ".")

    # 언어 설정 대화상자 대기
    _wait_for_new_window(before_titles, timeout=DEFAULT_TIMEOUT)
    time.sleep(0.3)

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

    # 마지막 Enter → 확인 버튼 (대화상자 닫힘 대기)
    pyautogui.press("enter")
    time.sleep(0.5)


def _wait_for_ocr_complete():
    """OCR 편집기에서 자동 OCR 처리 완료 대기 (창 제목 변화 감지)

    ABBYY는 OCR 처리중 진행 대화상자를 표시함.
    해당 대화상자가 사라지면 완료로 판단.
    """
    logger.info("OCR 처리 완료 대기중...")

    # OCR 진행 대화상자/상태가 나타나는지 잠시 대기
    time.sleep(2)

    # "인식" 또는 "Recogni" 키워드가 포함된 창(진행 대화상자)이 사라질 때까지 대기
    # ABBYY는 처리중 "인식 중..." / "Recognizing..." 등의 대화상자를 표시
    ocr_keywords = ["인식", "Recogni", "Progress", "진행", "처리"]

    # 먼저 진행 대화상자가 있는지 확인
    found_progress = False
    for kw in ocr_keywords:
        if _find_window(kw):
            found_progress = True
            logger.info(f"OCR 진행 대화상자 발견 ('{kw}')")
            # 해당 대화상자가 닫힐 때까지 대기
            _wait_for_window_gone(kw, timeout=LONG_TIMEOUT)
            break

    if not found_progress:
        # 진행 대화상자를 못 찾으면 짧게 대기 후 진행
        logger.info("OCR 진행 대화상자 미발견 — 3초 대기 후 진행")
        time.sleep(3)

    logger.info("OCR 처리 완료")


def _save_as_searchable_pdf(output_path: Path):
    """F10 → Enter → F → V → S → 검색 가능한 PDF로 저장"""
    logger.info(f"검색 가능한 PDF로 저장: {output_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    before_titles = _get_window_titles()

    # F10 → Enter → F → V → S 로 저장 대화상자 열기
    pyautogui.press("f10")
    time.sleep(0.5)
    pyautogui.press("enter")
    time.sleep(0.3)
    pyautogui.press("f")
    time.sleep(0.3)
    pyautogui.press("v")
    time.sleep(0.3)
    pyautogui.press("s")

    # 저장 대화상자가 열릴 때까지 대기
    _wait_for_new_window(before_titles, timeout=DEFAULT_TIMEOUT)
    time.sleep(0.5)

    # 저장 대화상자에서 파일명 입력 (_ocr 붙인 전체 경로)
    pyperclip.copy(str(output_path))
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.3)

    # 저장 실행 → 대화상자가 닫힐 때까지 대기
    pyautogui.press("enter")

    # 저장 완료 대기: 저장 대화상자가 사라질 때까지
    # "저장" / "Save" 키워드로 감지
    save_keywords = ["저장", "Save"]
    for kw in save_keywords:
        if _find_window(kw):
            _wait_for_window_gone(kw, timeout=DEFAULT_TIMEOUT)
            break
    else:
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

    # 4. OCR 완료 대기 (창 감지 기반)
    _wait_for_ocr_complete()

    # 5. F10 → Enter → F → V → S → 검색 가능한 PDF로 저장
    _save_as_searchable_pdf(output_path)

    # 6. 문서 닫기
    _close_document()

    logger.info(f"OCR 완료: {output_path.name}")
    return output_path
