"""PDF 합치기"""

import gc
import shutil
from pathlib import Path
import fitz


def count_pages(pdf_path: Path) -> int:
    """PDF 페이지 수. 처리 전후 페이지 누락 검증용."""
    doc = fitz.open(pdf_path)
    n = len(doc)
    doc.close()
    del doc
    gc.collect()
    return n


def merge_pdfs(pdf_files: list[Path], output_path: Path) -> Path:
    """여러 PDF를 하나로 합침. 1개면 그대로 복사."""
    if len(pdf_files) == 1:
        if pdf_files[0] != output_path:
            shutil.copy2(pdf_files[0], output_path)
        return output_path

    merged = fitz.open()
    for pdf_file in pdf_files:
        doc = fitz.open(pdf_file)
        merged.insert_pdf(doc)
        doc.close()
        del doc
    merged.save(str(output_path), garbage=4, deflate=True)
    merged.close()
    del merged
    gc.collect()
    return output_path
