"""ABBYY FineReader PDF 16 편집기 레벨 조정 자동화 (pyautogui)

ABBYY 편집기를 실행하여 이미지 레벨 조정 후 저장.
고급 스캔 시 사용.

흐름:
1. ABBYY FineReader PDF 16 프로그램 실행
2. Ctrl+R → 파일 경로 입력 → Enter
3. (OCR인 경우) Ctrl+. → 언어 설정
4. Ctrl+I → 이미지 편집기 → L → 레벨 조정
5. Ctrl+S → 저장 대화상자 → 파일 형식 선택 → 저장
"""

import os
import subprocess
import time
import logging
from pathlib import Path

import pyautogui
import pyperclip

from automation.pipeline.ocr import (
    _find_abbyy_window,
    _wait_for_abbyy,
    _wait_for_file_complete,
    _close_abbyy,
    _set_language,
    _log_timeout_diagnostic,
)

logger = logging.getLogger(__name__)

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.3

# ABBYY OCR 편집기 실행 경로
ABBYY_OCR_EXE = r"C:\Program Files\ABBYY FineReader 16\FineReaderOCR.exe"

LOADING_POLL_INTERVAL = 0.5
LOADING_TIMEOUT = 2400  # 40분


# ── ABBYY 편집기 실행 ──────────────────────────────────────────

def _open_in_ocr_editor(pdf_path: Path):
    """FineReaderOCR.exe로 PDF를 OCR 편집기에서 바로 열기

    창 제목에 파일명이 나타날 때까지 대기하여 파일이 완전히 로드된 후 진행.
    """
    if not os.path.exists(ABBYY_OCR_EXE):
        raise RuntimeError(f"ABBYY OCR 편집기를 찾을 수 없습니다: {ABBYY_OCR_EXE}")

    logger.info(f"OCR 편집기에서 파일 열기: {pdf_path}")
    subprocess.Popen([ABBYY_OCR_EXE, str(pdf_path)])

    if not _wait_for_abbyy(timeout=60):
        raise RuntimeError("ABBYY FineReader가 실행되지 않습니다")

    # 창 제목에 파일명이 나타날 때까지 대기 (파일 로드 완료 감지)
    import pygetwindow as gw
    file_stem = pdf_path.stem
    start = time.time()
    while time.time() - start < 20:
        for win in gw.getAllWindows():
            if file_stem in win.title:
                logger.info(f"파일 로드 완료: '{win.title}'")
                time.sleep(2)
                _find_abbyy_window()
                return
        time.sleep(1)

    logger.warning("파일명이 창 제목에 나타나지 않음 - 계속 진행")
    _find_abbyy_window()


# ── 레벨 조정 ──────────────────────────────────────────────────

def _enter_image_editor():
    """Ctrl+I → 이미지 편집기 모드 진입"""
    pyautogui.hotkey("ctrl", "i")
    time.sleep(10)


def _apply_levels(black_point: int, white_point: int):
    """레벨 도구에서 black/white point 입력 및 적용

    L → Tab → black → Tab×2 → white → Tab×4 → Down×3 → Enter → P → P → Enter → Enter
    """
    logger.info(f"레벨 조정: black={black_point}, white={white_point}")

    pyautogui.press("l")
    time.sleep(1.5)

    # Tab 1번 → black_point 붙여넣기
    pyautogui.press("tab")
    time.sleep(1.5)
    pyperclip.copy(str(black_point))
    pyautogui.hotkey("ctrl", "a")
    time.sleep(1.5)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(1.5)

    # Tab 2번 → white_point 붙여넣기
    for _ in range(2):
        pyautogui.press("tab")
        time.sleep(1.5)
    pyperclip.copy(str(white_point))
    pyautogui.hotkey("ctrl", "a")
    time.sleep(1.5)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(1.5)

    # Tab 4번 → Down 3번
    for _ in range(4):
        pyautogui.press("tab")
        time.sleep(1.5)
    for _ in range(3):
        pyautogui.press("down")
        time.sleep(1.5)

    # Enter → P → P → Enter(확인) → Enter
    pyautogui.press("enter")
    time.sleep(1.5)
    pyautogui.press("p")
    time.sleep(1.5)
    pyautogui.press("p")
    time.sleep(1.5)
    pyautogui.press("enter")
    time.sleep(1.5)
    pyautogui.press("enter")
    time.sleep(1.5)


def _check_loading_window(gw, loading_title: str) -> bool:
    """로딩 창이 현재 떠있는지 확인"""
    for win in gw.getAllWindows():
        if loading_title in win.title:
            return True
    return False


def _wait_for_loading_gone(gw, loading_title: str, timeout: int = LOADING_TIMEOUT):
    """Phase 2: 로딩 창이 사라질 때까지 대기"""
    start = time.time()
    while time.time() - start < timeout:
        if not _check_loading_window(gw, loading_title):
            logger.info(f"레벨 처리 완료 ({time.time() - start:.0f}초)")
            time.sleep(3)
            _find_abbyy_window()
            return False
        time.sleep(LOADING_POLL_INTERVAL)
    _log_timeout_diagnostic("레벨 처리 (로딩 창 사라짐 대기)")
    raise RuntimeError(f"레벨 처리 타임아웃 ({timeout}초)")


def _wait_for_processing(timeout: int = LOADING_TIMEOUT, detect_timeout: int = 180) -> bool:
    """레벨 처리 완료 대기

    Returns:
        True: Ctrl+S로 저장 대화상자가 이미 열림 (Phase 3)
        False: 로딩 창 감지로 완료 확인 (Phase 1/2)
    """
    import pygetwindow as gw

    LOADING_TITLE = "이미지를 처리하는 중"
    CTRL_S_INTERVAL = 180  # 3분

    logger.info("레벨 처리 완료 대기중...")
    start = time.time()

    # Phase 1: 로딩 창 감지 대기 (최초 3분)
    loading_appeared = False
    while time.time() - start < detect_timeout:
        if _check_loading_window(gw, LOADING_TITLE):
            loading_appeared = True
            logger.info("로딩 창 감지")
            break
        time.sleep(LOADING_POLL_INTERVAL)

    # Phase 2: 로딩 창이 떴으면 사라질 때까지 대기
    if loading_appeared:
        return _wait_for_loading_gone(gw, LOADING_TITLE, timeout)

    # Phase 3: 로딩 창 미감지 → 3분마다 Ctrl+S 시도 + 로딩 창 감지 병행
    logger.info("로딩 창 미감지 - Ctrl+S로 완료 확인 시작")
    while time.time() - start < timeout:
        # Ctrl+S 시도
        _find_abbyy_window()
        time.sleep(1)
        pyautogui.hotkey("ctrl", "s")
        time.sleep(2)

        if _detect_save_dialog():
            logger.info(f"Ctrl+S로 저장 대화상자 감지 ({time.time() - start:.0f}초)")
            return True

        # 3분 대기하면서 로딩 창 감지 병행
        wait_start = time.time()
        while time.time() - wait_start < CTRL_S_INTERVAL:
            if _check_loading_window(gw, LOADING_TITLE):
                logger.info("대기 중 로딩 창 감지 → Phase 2로 전환")
                return _wait_for_loading_gone(gw, LOADING_TITLE, timeout)
            time.sleep(LOADING_POLL_INTERVAL)

    _log_timeout_diagnostic("레벨 처리 (Ctrl+S 폴백)")
    raise RuntimeError(f"레벨 처리 타임아웃 ({timeout}초)")


# ── 저장 ──────────────────────────────────────────────────────

def _detect_save_dialog(timeout: int = 3) -> bool:
    """'문서를 다른 이름으로 저장' 대화상자 감지"""
    import pygetwindow as gw
    start = time.time()
    while time.time() - start < timeout:
        for win in gw.getAllWindows():
            if "저장" in win.title:
                return True
        time.sleep(0.5)
    return False


def _open_save_dialog(output_path: Path, file_type_index: int,
                      skip_open: bool = False):
    """Ctrl+S로 저장 대화상자를 열고 경로 입력 + 파일 형식 선택

    Args:
        output_path: 저장할 파일 경로
        file_type_index: 파일 형식 드롭다운 인덱스 (1-based, 위에서부터)
            5 = 검색 가능한 PDF 문서
            6 = 이미지 전용 PDF 문서
        skip_open: True면 저장 대화상자가 이미 열려있으므로 Esc+Ctrl+S 스킵
    """
    if not skip_open:
        _find_abbyy_window()
        time.sleep(1)
        pyautogui.press("escape")  # 이미지 편집기 모드 해제
        time.sleep(1)
        pyautogui.hotkey("ctrl", "s")
        time.sleep(2)

        if not _detect_save_dialog():
            raise RuntimeError("저장 대화상자 열기 실패")
    logger.info("저장 대화상자 감지")

    # 경로 입력 (파일 이름이 전체 선택 상태)
    pyperclip.copy(str(output_path))
    pyautogui.hotkey("ctrl", "v")
    time.sleep(1)

    # 파일 형식 선택: Alt+Shift+T → Down(드롭다운 열기) → Up 15번(맨 위) → Down (index-1)번
    pyautogui.press("tab")
    time.sleep(1)
    pyautogui.press("down")
    time.sleep(1)
    pyautogui.press("home")
    for _ in range(file_type_index - 1):
        pyautogui.press("down")
    pyautogui.press("enter")
    time.sleep(1)


def _save_as_image_pdf(output_path: Path, dialog_already_open: bool = False):
    """Ctrl+S → 경로 입력 → 이미지 전용 PDF 선택 → 저장"""
    logger.info(f"이미지 PDF로 저장: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    _open_save_dialog(output_path, file_type_index=6,
                      skip_open=dialog_already_open)
    pyautogui.press("enter")

    _wait_for_file_complete(output_path)
    logger.info(f"저장 완료: {output_path}")


def _save_as_searchable_pdf(output_path: Path, dialog_already_open: bool = False):
    """Ctrl+S → 경로 입력 → 검색 가능한 PDF 선택 → 저장"""
    logger.info(f"검색 가능 PDF로 저장: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    _open_save_dialog(output_path, file_type_index=5,
                      skip_open=dialog_already_open)
    pyautogui.press("enter")
    time.sleep(2)
    pyautogui.press("enter")  # OCR 안내창 닫기

    _wait_for_file_complete(output_path)
    logger.info(f"저장 완료: {output_path}")


# ── 공개 API ──────────────────────────────────────────────────

def run_ocr_only(input_path: Path, output_path: Path,
                 languages: list[str] | str = "Korean") -> Path:
    """일반+OCR: 색상 보정 없이 ABBYY OCR 편집기에서 검색 가능 PDF로 저장"""
    if isinstance(languages, str):
        languages = [languages]

    logger.info(f"OCR 시작 (일반): {input_path.name}")

    try:
        _open_in_ocr_editor(input_path)
        _set_language(languages)
        _save_as_searchable_pdf(output_path)
    finally:
        _close_abbyy()

    logger.info(f"OCR 완료: {output_path.name}")
    return output_path


def run_levels_only(input_path: Path, output_path: Path,
                    black_point: int, white_point: int) -> Path:
    """고급만: ABBYY 편집기에서 레벨 조정 후 이미지 PDF로 저장"""
    logger.info(f"레벨 조정 시작 (고급): {input_path.name}")

    try:
        _open_in_ocr_editor(input_path)
        _enter_image_editor()
        _apply_levels(black_point, white_point)
        dialog_open = _wait_for_processing()
        _save_as_image_pdf(output_path, dialog_already_open=dialog_open)
    finally:
        _close_abbyy()

    logger.info(f"레벨 조정 완료: {output_path.name}")
    return output_path


def run_levels_with_ocr(input_path: Path, output_path: Path,
                        black_point: int, white_point: int,
                        languages: list[str] | str = "Korean") -> Path:
    """고급+OCR: ABBYY 편집기에서 언어설정 + 레벨 조정 후 검색가능 PDF로 저장"""
    if isinstance(languages, str):
        languages = [languages]

    logger.info(f"레벨+OCR 시작 (고급+OCR): {input_path.name}")

    try:
        _open_in_ocr_editor(input_path)
        _set_language(languages)
        _enter_image_editor()
        _apply_levels(black_point, white_point)
        dialog_open = _wait_for_processing()
        _save_as_searchable_pdf(output_path, dialog_already_open=dialog_open)
    finally:
        _close_abbyy()

    logger.info(f"레벨+OCR 완료: {output_path.name}")
    return output_path
