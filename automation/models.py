"""작업 모델 정의"""

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class JobStatus(Enum):
    WAITING = "대기중"
    RUNNING = "작업중"
    DONE = "완료"
    ERROR = "오류"


@dataclass
class BookConfig:
    type: str = "일반"
    black_point: int = 0
    white_point: int = 255
    ocr_language: str = "Korean"
    split_after_ocr: bool = False
    split_by_pages: str = ""
    split_by_size: int = 0

    @classmethod
    def from_file(cls, path: Path) -> "BookConfig":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(
            type=data.get("type", "일반"),
            black_point=data.get("black_point", 0),
            white_point=data.get("white_point", 255),
            ocr_language=data.get("ocr_language", "Korean"),
            split_after_ocr=data.get("split_after_ocr", False),
            split_by_pages=data.get("split_by_pages", ""),
            split_by_size=data.get("split_by_size", 0),
        )


@dataclass
class Job:
    customer_name: str
    book_name: str
    book_dir: Path
    config: BookConfig
    status: JobStatus = JobStatus.WAITING
    current_step: str = ""
    error_message: str = ""
    pdf_files: list = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return f"{self.customer_name} / {self.book_name}"

    def get_pdf_files(self) -> list:
        if not self.pdf_files:
            self.pdf_files = sorted(self.book_dir.glob("*.pdf"))
        return self.pdf_files
