"""작업 모델 정의"""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


_CUSTOMER_SUFFIX_RE = re.compile(r"^(?P<name>.+)-(?P<count>\d+)$")
_NUM_RE = re.compile(r"(\d+)")

CROP_SIDES = ("top", "bottom", "left", "right")


def parse_crop_mm(value) -> dict:
    """config.json의 crop_mm을 {top, bottom, left, right} (mm, float)으로 정규화.

    pdf-level-preview가 네 방향 값을 객체로 쓴다. 구버전은 숫자 하나로 적었으므로
    그 경우 네 방향 모두 같은 값으로 읽는다. 없거나 이상한 값이면 전부 0.
    """
    def num(v):
        try:
            return max(0.0, float(v))
        except (TypeError, ValueError):
            return 0.0

    if isinstance(value, dict):
        return {s: num(value.get(s)) for s in CROP_SIDES}
    if isinstance(value, (int, float)):
        return {s: num(value) for s in CROP_SIDES}
    return {s: 0.0 for s in CROP_SIDES}


def natural_key(name: str) -> list:
    """파일명 속 숫자를 수치로 비교하는 정렬 키.

    "Image_2.pdf" < "Image_10.pdf" (문자열 정렬이면 반대)
    번호는 순서만 정하며 연속일 필요는 없다 (Image_005 다음이 Image_008이어도 정상).
    """
    return [int(t) if t.isdigit() else t.lower() for t in _NUM_RE.split(name)]


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
    crop_mm: dict = None  # 여백 자르기 {top, bottom, left, right} (mm)

    def __post_init__(self):
        if self.ocr_language is None:
            self.ocr_language = ["한국어"]
        self.crop_mm = parse_crop_mm(self.crop_mm)

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
            crop_mm=data.get("crop_mm"),
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
    part_label: str = ""  # PDF 여러 개일 때 진행 표시 접두사 ("[2/3] ")

    def __post_init__(self):
        if not self.customer_folder_name:
            self.customer_folder_name = self.customer_name

    @property
    def display_name(self) -> str:
        return f"{self.customer_folder_name} / {self.book_name}"

    def get_pdf_files(self) -> list:
        if not self.pdf_files:
            self.pdf_files = sorted(self.book_dir.glob("*.pdf"),
                                    key=lambda p: natural_key(p.name))
        return self.pdf_files
