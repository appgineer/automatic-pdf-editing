"""오류 로그 파일 핸들러 관리"""

import logging
from pathlib import Path

_error_log_handler = None


def setup_error_log(output_dir: Path):
    """출력폴더에 오류로그.txt 파일 핸들러 추가.

    WARNING 이상 로그만 기록되며, delay=True로 첫 오류 발생 시에만 파일 생성됨.
    이미 핸들러가 등록되어 있으면 제거 후 새로 추가 (출력폴더 변경 대응).
    """
    global _error_log_handler

    root_logger = logging.getLogger()
    if _error_log_handler is not None:
        root_logger.removeHandler(_error_log_handler)
        _error_log_handler.close()
        _error_log_handler = None

    log_path = output_dir / "오류로그.txt"
    handler = logging.FileHandler(log_path, mode="a", encoding="utf-8", delay=True)
    handler.setLevel(logging.WARNING)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    root_logger.addHandler(handler)
    _error_log_handler = handler
