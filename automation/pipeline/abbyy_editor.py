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
    _list_abbyy_windows,
    _ActivityWatch,
)

logger = logging.getLogger(__name__)

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.3

# ABBYY OCR 편집기 실행 경로
ABBYY_OCR_EXE = r"C:\Program Files\ABBYY FineReader 16\FineReaderOCR.exe"

LOADING_POLL_INTERVAL = 0.5


# ── ABBYY 편집기 실행 ──────────────────────────────────────────

def _open_in_ocr_editor(pdf_path: Path):
    """FineReaderOCR.exe로 PDF를 OCR 편집기에서 바로 열기

    창 제목에 파일명이 나타날 때까지 대기하여 파일이 완전히 로드된 후 진행.
    """
    if not os.path.exists(ABBYY_OCR_EXE):
        raise RuntimeError(f"ABBYY OCR 편집기를 찾을 수 없습니다: {ABBYY_OCR_EXE}")

    logger.info(f"[열기] 시작: {pdf_path}")

    logger.info(f"[열기 1/3] ABBYY 실행 명령: FineReaderOCR.exe \"{pdf_path}\"")
    subprocess.Popen([ABBYY_OCR_EXE, str(pdf_path)])

    logger.info("[열기 2/3] ABBYY 프로세스/창 감지 대기 (최대 60초)")
    proc_start = time.time()
    if not _wait_for_abbyy(timeout=60):
        logger.error(f"[열기 2/3] ABBYY 창 감지 실패 - 보이는 ABBYY 관련 창: {_list_abbyy_windows()}")
        raise RuntimeError("ABBYY FineReader가 실행되지 않습니다")
    logger.info(f"[열기 2/3] ABBYY 창 감지 OK ({time.time() - proc_start:.1f}초)")

    # 창 제목에 파일명이 나타날 때까지 대기 (파일 로드 완료 감지)
    import pygetwindow as gw
    file_stem = pdf_path.stem
    logger.info(f"[열기 3/3] 파일 로드 감지 대기 — 창 제목에 '{file_stem}' 등장 대기 (20초)")
    start = time.time()
    while time.time() - start < 20:
        for win in gw.getAllWindows():
            if file_stem in win.title:
                logger.info(f"[열기 3/3] 파일 로드 완료 ({time.time() - start:.1f}초): '{win.title}'")
                time.sleep(2)
                _find_abbyy_window()
                logger.info("[열기] 완료")
                return
        time.sleep(1)

    visible = _list_abbyy_windows()
    logger.warning(f"[열기 3/3] ⚠ 파일명 미감지 (20초 경과) - 보이는 ABBYY 관련 창: {visible}")
    if any(("무제" in t) or ("Untitled" in t) for t in visible):
        logger.warning("[열기 3/3] ⚠ '무제 프로젝트' 상태로 보임 → ABBYY가 인자로 받은 파일을 못 연 듯 (KVM/포커스 영향 의심)")
    logger.warning("[열기 3/3] 그대로 계속 진행 — 이후 단축키가 빈 프로젝트에 적용될 수 있음")
    _find_abbyy_window()
    logger.info("[열기] 종료 (경고와 함께)")


# ── 레벨 조정 ──────────────────────────────────────────────────

def _enter_image_editor():
    """Ctrl+I → 이미지 편집기 모드 진입"""
    logger.info("[이미지편집기] Ctrl+I (모드 진입)")
    pyautogui.hotkey("ctrl", "i")
    logger.info("[이미지편집기] 진입 대기 10초")
    time.sleep(10)
    logger.info("[이미지편집기] 완료")


def _apply_levels(black_point: int, white_point: int):
    """레벨 도구에서 black/white point 입력 및 적용

    L → Tab → black → Tab×2 → white → Tab×4 → Down×3 → Enter → P → P → Enter → Enter
    """
    logger.info(f"[레벨] 시작 (black={black_point}, white={white_point})")

    logger.info("[레벨 1/6] L (레벨 도구 열기)")
    pyautogui.press("l")
    time.sleep(1.5)

    # Tab 1번 → black_point 붙여넣기
    logger.info(f"[레벨 2/6] Tab → black point '{black_point}' 입력")
    pyautogui.press("tab")
    logger.info("[레벨 2/6]  - Tab 1/1")
    time.sleep(1.5)
    pyperclip.copy(str(black_point))
    pyautogui.hotkey("ctrl", "a")
    logger.info("[레벨 2/6]  - Ctrl+A (전체 선택)")
    time.sleep(1.5)
    pyautogui.hotkey("ctrl", "v")
    logger.info("[레벨 2/6]  - Ctrl+V (붙여넣기)")
    time.sleep(1.5)

    # Tab 2번 → white_point 붙여넣기
    logger.info(f"[레벨 3/6] Tab×2 → white point '{white_point}' 입력")
    for i in range(2):
        pyautogui.press("tab")
        logger.info(f"[레벨 3/6]  - Tab {i+1}/2")
        time.sleep(1.5)
    pyperclip.copy(str(white_point))
    pyautogui.hotkey("ctrl", "a")
    logger.info("[레벨 3/6]  - Ctrl+A (전체 선택)")
    time.sleep(1.5)
    pyautogui.hotkey("ctrl", "v")
    logger.info("[레벨 3/6]  - Ctrl+V (붙여넣기)")
    time.sleep(1.5)

    # Tab 4번 → Down 3번
    logger.info("[레벨 4/6] Tab×4 (드롭다운 이동)")
    for i in range(4):
        pyautogui.press("tab")
        logger.info(f"[레벨 4/6]  - Tab {i+1}/4")
        time.sleep(1.5)
    logger.info("[레벨 5/6] Down×3 (드롭다운 항목 이동)")
    for i in range(3):
        pyautogui.press("down")
        logger.info(f"[레벨 5/6]  - Down {i+1}/3")
        time.sleep(1.5)

    # Enter → P → P → Enter(확인) → Enter
    logger.info("[레벨 6/6] 적용 시퀀스 (Enter → P → P → Enter → Enter)")
    pyautogui.press("enter")
    logger.info("[레벨 6/6]  - Enter (1)")
    time.sleep(1.5)
    pyautogui.press("p")
    logger.info("[레벨 6/6]  - P (1)")
    time.sleep(1.5)
    pyautogui.press("p")
    logger.info("[레벨 6/6]  - P (2)")
    time.sleep(1.5)
    pyautogui.press("enter")
    logger.info("[레벨 6/6]  - Enter (2 = 확인)")
    time.sleep(1.5)
    pyautogui.press("enter")
    logger.info("[레벨 6/6]  - Enter (3)")
    time.sleep(1.5)
    logger.info("[레벨] 완료")


def _check_loading_window(gw, loading_title: str) -> bool:
    """로딩 창이 현재 떠있는지 확인"""
    for win in gw.getAllWindows():
        if loading_title in win.title:
            return True
    return False


def _wait_for_loading_gone(gw, loading_title: str) -> bool:
    """Phase 2: 로딩 창이 사라질 때까지 대기 (활동 없이 멈추면 중단)"""
    logger.info(f"[처리대기 Phase2] 로딩 창 '{loading_title}' 사라짐 대기 (활동 기반)")
    start = time.time()
    last_progress = 0.0
    watch = _ActivityWatch("레벨 처리 (로딩 창 사라짐 대기)")
    while True:
        if not _check_loading_window(gw, loading_title):
            logger.info(f"[처리대기 Phase2] 로딩 창 사라짐 = 레벨 처리 완료 ({time.time() - start:.0f}초)")
            time.sleep(3)
            _find_abbyy_window()
            return False
        # 60초마다 진행 로그
        elapsed = time.time() - start
        if elapsed - last_progress >= 60:
            last_progress = elapsed
            logger.info(f"[처리대기 Phase2] {elapsed:.0f}초 경과 - 로딩 창 여전히 떠있음")
        watch.tick()  # 창이 떠 있어도 CPU idle이면 멈춤(얼어붙음)으로 중단
        time.sleep(LOADING_POLL_INTERVAL)


def _wait_for_processing(detect_timeout: int = 180) -> bool:
    """레벨 처리 완료 대기

    Returns:
        True: Ctrl+S로 저장 대화상자가 이미 열림 (Phase 3)
        False: 로딩 창 감지로 완료 확인 (Phase 1/2)
    """
    import pygetwindow as gw

    LOADING_TITLE = "이미지를 처리하는 중"
    CTRL_S_INTERVAL = 180  # 3분

    logger.info(f"[처리대기] 시작 - Phase1: 로딩 창 '{LOADING_TITLE}' 감지 (최대 {detect_timeout}초)")
    start = time.time()

    # Phase 1: 로딩 창 감지 대기 (최초 3분)
    loading_appeared = False
    while time.time() - start < detect_timeout:
        if _check_loading_window(gw, LOADING_TITLE):
            loading_appeared = True
            logger.info(f"[처리대기 Phase1] 로딩 창 감지 ({time.time() - start:.0f}초)")
            break
        time.sleep(LOADING_POLL_INTERVAL)

    # Phase 2: 로딩 창이 떴으면 사라질 때까지 대기
    if loading_appeared:
        return _wait_for_loading_gone(gw, LOADING_TITLE)

    # Phase 3: 로딩 창 미감지 → 3분마다 Ctrl+S 시도 + 로딩 창/멈춤 감지 병행
    logger.warning(f"[처리대기 Phase1] {detect_timeout}초 동안 로딩 창 미감지 - 보이는 창: {_list_abbyy_windows()}")
    logger.info(f"[처리대기 Phase3] Ctrl+S 폴백 모드 시작 ({CTRL_S_INTERVAL}초 간격으로 Ctrl+S 시도)")
    watch = _ActivityWatch("레벨 처리 (Ctrl+S 폴백)")
    while True:
        logger.info(f"[처리대기 Phase3] Ctrl+S 시도 ({time.time() - start:.0f}초 경과)")
        _find_abbyy_window()
        time.sleep(1)
        pyautogui.hotkey("ctrl", "s")
        time.sleep(2)

        if _detect_save_dialog():
            logger.info(f"[처리대기 Phase3] Ctrl+S로 저장 대화상자 감지 ({time.time() - start:.0f}초)")
            return True

        # 다음 Ctrl+S까지 대기하면서 로딩 창 감지 + 멈춤 감지 병행
        wait_start = time.time()
        while time.time() - wait_start < CTRL_S_INTERVAL:
            if _check_loading_window(gw, LOADING_TITLE):
                logger.info("[처리대기 Phase3→Phase2] 대기 중 로딩 창 감지 → Phase2 전환")
                return _wait_for_loading_gone(gw, LOADING_TITLE)
            watch.tick()  # 활동 없이 STUCK_IDLE_LIMIT 지나면 멈춤으로 중단
            time.sleep(LOADING_POLL_INTERVAL)


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
    fmt_name = {5: "검색 가능한 PDF", 6: "이미지 전용 PDF"}.get(file_type_index, f"index={file_type_index}")
    logger.info(f"[저장대화] 시작 (형식={fmt_name}, 경로={output_path})")

    if not skip_open:
        logger.info("[저장대화 1/5] ABBYY 본 창 활성화")
        _find_abbyy_window()
        time.sleep(1)
        logger.info("[저장대화 2/5] Escape (이미지 편집기 모드 해제)")
        pyautogui.press("escape")
        time.sleep(1)
        logger.info("[저장대화 3/5] Ctrl+S (저장 대화상자 열기)")
        pyautogui.hotkey("ctrl", "s")
        time.sleep(2)

        if not _detect_save_dialog():
            visible = _list_abbyy_windows()
            logger.error(f"[저장대화 3/5] ⚠ 저장 대화상자 감지 실패 - 보이는 창: {visible}")
            raise RuntimeError("저장 대화상자 열기 실패")
        logger.info("[저장대화 3/5] 저장 대화상자 감지 OK")
    else:
        logger.info("[저장대화 1-3/5] 대화상자 이미 열림 — 건너뜀")
        logger.info("[저장대화 3/5] 저장 대화상자 감지 OK (skip_open)")

    # 경로 입력 (파일 이름이 전체 선택 상태)
    logger.info(f"[저장대화 4/5] 경로 붙여넣기 (Ctrl+V): '{output_path}'")
    pyperclip.copy(str(output_path))
    pyautogui.hotkey("ctrl", "v")
    time.sleep(1)

    # 파일 형식 선택: Tab → Down → Home → Down×(index-1) → Enter
    logger.info(f"[저장대화 5/5] 파일 형식 선택 시퀀스 — Tab → Down → Home → Down×{file_type_index - 1} → Enter")
    pyautogui.press("tab")
    logger.info("[저장대화 5/5]  - Tab (파일 형식 드롭다운으로 이동)")
    time.sleep(1)
    pyautogui.press("down")
    logger.info("[저장대화 5/5]  - Down (드롭다운 열기)")
    time.sleep(1)
    pyautogui.press("home")
    logger.info("[저장대화 5/5]  - Home (드롭다운 맨 위로)")
    for i in range(file_type_index - 1):
        pyautogui.press("down")
        logger.info(f"[저장대화 5/5]  - Down {i+1}/{file_type_index - 1} (형식={fmt_name} 도달)")
    pyautogui.press("enter")
    logger.info(f"[저장대화 5/5]  - Enter (형식 선택 확정 = {fmt_name})")
    time.sleep(1)
    logger.info("[저장대화] 완료 (이제 최종 Enter 한 번 더 누르면 저장 시작)")


def _save_as_image_pdf(output_path: Path, dialog_already_open: bool = False):
    """Ctrl+S → 경로 입력 → 이미지 전용 PDF 선택 → 저장"""
    logger.info(f"[저장-이미지PDF] 시작: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    _open_save_dialog(output_path, file_type_index=6,
                      skip_open=dialog_already_open)
    logger.info("[저장-이미지PDF] 최종 Enter (저장 시작)")
    pyautogui.press("enter")

    _wait_for_file_complete(output_path)
    logger.info(f"[저장-이미지PDF] 완료: {output_path}")


def _save_as_searchable_pdf(output_path: Path, dialog_already_open: bool = False):
    """Ctrl+S → 경로 입력 → 검색 가능한 PDF 선택 → 저장"""
    logger.info(f"[저장-검색가능PDF] 시작: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    _open_save_dialog(output_path, file_type_index=5,
                      skip_open=dialog_already_open)
    logger.info("[저장-검색가능PDF] 최종 Enter (저장 시작)")
    pyautogui.press("enter")
    time.sleep(2)
    logger.info("[저장-검색가능PDF] Enter (OCR 안내창 닫기)")
    pyautogui.press("enter")

    _wait_for_file_complete(output_path)
    logger.info(f"[저장-검색가능PDF] 완료: {output_path}")


# ── 공개 API ──────────────────────────────────────────────────

def run_ocr_only(input_path: Path, output_path: Path,
                 languages: list[str] | str = "Korean") -> Path:
    """일반+OCR: 색상 보정 없이 ABBYY OCR 편집기에서 검색 가능 PDF로 저장"""
    if isinstance(languages, str):
        languages = [languages]

    logger.info(f"===== [일반+OCR] 시작: {input_path.name} → {output_path.name} =====")
    logger.info("[일반+OCR] 단계 순서: 열기 → 언어 → 저장-검색가능PDF → 저장대기")

    try:
        _open_in_ocr_editor(input_path)
        _set_language(languages)
        _save_as_searchable_pdf(output_path)
    finally:
        logger.info("[일반+OCR] ABBYY 종료 단계")
        _close_abbyy()

    logger.info(f"===== [일반+OCR] 완료: {output_path.name} =====")
    return output_path


def run_levels_only(input_path: Path, output_path: Path,
                    black_point: int, white_point: int) -> Path:
    """고급만: ABBYY 편집기에서 레벨 조정 후 이미지 PDF로 저장"""
    logger.info(f"===== [고급] 시작: {input_path.name} → {output_path.name} =====")
    logger.info("[고급] 단계 순서: 열기 → 이미지편집기 → 레벨 → 처리대기 → 저장-이미지PDF → 저장대기")

    try:
        _open_in_ocr_editor(input_path)
        _enter_image_editor()
        _apply_levels(black_point, white_point)
        dialog_open = _wait_for_processing()
        _save_as_image_pdf(output_path, dialog_already_open=dialog_open)
    finally:
        logger.info("[고급] ABBYY 종료 단계")
        _close_abbyy()

    logger.info(f"===== [고급] 완료: {output_path.name} =====")
    return output_path


def run_levels_with_ocr(input_path: Path, output_path: Path,
                        black_point: int, white_point: int,
                        languages: list[str] | str = "Korean") -> Path:
    """고급+OCR: ABBYY 편집기에서 언어설정 + 레벨 조정 후 검색가능 PDF로 저장"""
    if isinstance(languages, str):
        languages = [languages]

    logger.info(f"===== [고급+OCR] 시작: {input_path.name} → {output_path.name} =====")
    logger.info("[고급+OCR] 단계 순서: 열기 → 언어 → 이미지편집기 → 레벨 → 처리대기 → 저장-검색가능PDF → 저장대기")

    try:
        _open_in_ocr_editor(input_path)
        _set_language(languages)
        _enter_image_editor()
        _apply_levels(black_point, white_point)
        dialog_open = _wait_for_processing()
        _save_as_searchable_pdf(output_path, dialog_already_open=dialog_open)
    finally:
        logger.info("[고급+OCR] ABBYY 종료 단계")
        _close_abbyy()

    logger.info(f"===== [고급+OCR] 완료: {output_path.name} =====")
    return output_path
