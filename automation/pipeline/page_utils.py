"""PDF 첫 페이지 복사/삭제 유틸리티"""

import gc
from pathlib import Path
import fitz


def prepend_first_page(input_path: Path, output_path: Path) -> Path:
    """PDF의 첫 페이지를 복사하여 맨 앞에 추가한 새 파일 생성.

    ABBYY 레벨 조정 시 첫 페이지가 적용되지 않는 버그 대응용.
    """
    doc = fitz.open(input_path)
    new_doc = fitz.open()
    new_doc.insert_pdf(doc, from_page=0, to_page=0)
    new_doc.insert_pdf(doc)
    new_doc.save(str(output_path))
    new_doc.close()
    doc.close()
    del new_doc, doc
    gc.collect()
    return output_path


def delete_first_page(input_path: Path, output_path: Path) -> Path:
    """PDF의 첫 페이지를 삭제한 새 파일 생성."""
    doc = fitz.open(input_path)
    doc.delete_page(0)
    doc.save(str(output_path))
    doc.close()
    del doc
    gc.collect()
    return output_path
