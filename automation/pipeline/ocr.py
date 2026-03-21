"""ABBYY FineReader OCR 자동화 (pyautogui)

Phase 4에서 B컴퓨터에서 구현 예정.
현재는 스텁으로 입력 파일을 그대로 반환.
"""

from pathlib import Path


def run_ocr(input_path: Path, output_path: Path, language: str = "Korean") -> Path:
    """ABBYY OCR 실행 (스텁 - Phase 4에서 구현)"""
    # TODO: pyautogui를 사용한 ABBYY FineReader 자동화
    # 1. ABBYY 실행/활성화
    # 2. 파일 열기
    # 3. OCR 언어 설정
    # 4. OCR 실행
    # 5. PDF로 저장
    # 6. 완료 대기

    import shutil
    if input_path != output_path:
        shutil.copy2(input_path, output_path)
    return output_path
