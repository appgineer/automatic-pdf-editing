"""작업 모델 정의"""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


_CUSTOMER_SUFFIX_RE = re.compile(r"^(?P<name>.+)-(?P<count>\d+)$")


def parse_customer_folder(folder_name: str) -> tuple[str, int | None]:
    """입력 폴더명에서 고객 이름과 권수를 추출.

    "박명수-3" → ("박명수", 3)
    "박명수"   → ("박명수", None)
    "a-b-2"   → ("a-b", 2)
    """
    m = _CUSTOMER_SUFFIX_RE.match(folder_name)
    if not m:
        return folder_name, None
    count = int(m.group("count"))
    if count <= 0:
        return folder_name, None
    return m.group("name"), count


class JobStatus(Enum):
    WAITING = "대기중"
    RUNNING = "작업중"
    DONE = "완료"
    ERROR = "오류"


@dataclass
class BookConfig:
    scan_type: str = "일반"
    black_point: int = 0
    white_point: int = 255
    ocr: bool = True
    ocr_language: list = None
    is_split: bool = False
    split_method: str = ""  # "page" 또는 "size"
    split_page_ranges: str = ""
    split_size_mb: int = 0

    def __post_init__(self):
        if self.ocr_language is None:
            self.ocr_language = ["한국어"]

    @classmethod
    def from_file(cls, path: Path) -> "BookConfig":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 언어: 문자열이면 리스트로 변환
        lang = data.get("ocr_language", ["한국어"])
        if isinstance(lang, str):
            lang = [lang]

        return cls(
            scan_type=data.get("scan_type", data.get("type", "일반")),
            black_point=data.get("black_point", 0),
            white_point=data.get("white_point", 255),
            ocr=data.get("ocr", True),
            ocr_language=lang,
            is_split=data.get("is_split", data.get("split_after_ocr", False)),
            split_method=data.get("split_method", ""),
            split_page_ranges=data.get("split_page_ranges", data.get("split_by_pages", "")),
            split_size_mb=data.get("split_size_mb", data.get("split_by_size", 0)),
        )


@dataclass
class Job:
    customer_name: str  # 접미사 제거된 이름 ("박명수")
    book_name: str
    book_dir: Path
    config: BookConfig
    customer_folder_name: str = ""  # 입력 폴더명 그대로 ("박명수-3")
    expected_count: int | None = None  # 총 권수 N
    status: JobStatus = JobStatus.WAITING
    current_step: str = ""
    error_message: str = ""
    pdf_files: list = field(default_factory=list)

    def __post_init__(self):
        if not self.customer_folder_name:
            self.customer_folder_name = self.customer_name

    @property
    def display_name(self) -> str:
        return f"{self.customer_folder_name} / {self.book_name}"

    def get_pdf_files(self) -> list:
        if not self.pdf_files:
            self.pdf_files = sorted(self.book_dir.glob("*.pdf"))
        return self.pdf_files
