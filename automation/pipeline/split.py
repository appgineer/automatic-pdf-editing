"""PDF 분할"""

import gc
from pathlib import Path
import fitz


def split_pdf_by_count(input_path: Path, max_pages: int, output_dir: Path, suffix: str = "_s") -> list[Path]:
    """PDF를 max_pages 단위로 분할. 결과 파일에 suffix 접미사 추가."""
    doc = fitz.open(input_path)
    total = len(doc)

    if total <= max_pages:
        doc.close()
        del doc
        gc.collect()
        return [input_path]

    stem = input_path.stem
    results = []
    part = 1

    for start in range(0, total, max_pages):
        end = min(start + max_pages, total)
        part_doc = fitz.open()
        part_doc.insert_pdf(doc, from_page=start, to_page=end - 1)

        out_name = f"{stem}{suffix}{part}.pdf"
        out_path = output_dir / out_name
        part_doc.save(str(out_path))
        part_doc.close()
        del part_doc
        results.append(out_path)
        part += 1

    doc.close()
    del doc
    gc.collect()
    return results


def split_pdf_by_page_ranges(input_path: Path, ranges_str: str, output_dir: Path) -> list[Path]:
    """'1-20,21-50' 형식으로 페이지 범위 분할"""
    if not ranges_str.strip():
        return [input_path]

    doc = fitz.open(input_path)
    stem = input_path.stem
    results = []

    ranges = [r.strip() for r in ranges_str.split(",") if r.strip()]
    for idx, page_range in enumerate(ranges, 1):
        parts = page_range.split("-")
        start = int(parts[0]) - 1  # 0-indexed
        end = int(parts[1]) if len(parts) > 1 else int(parts[0])

        part_doc = fitz.open()
        part_doc.insert_pdf(doc, from_page=start, to_page=end - 1)

        out_name = f"{stem}{idx}.pdf"
        out_path = output_dir / out_name
        part_doc.save(str(out_path))
        part_doc.close()
        del part_doc
        results.append(out_path)

    doc.close()
    del doc
    gc.collect()
    return results


def split_pdf_by_size(input_path: Path, max_size_mb: int, output_dir: Path) -> list[Path]:
    """파일 크기 기준 분할 (대략적)"""
    if max_size_mb <= 0:
        return [input_path]

    file_size_mb = input_path.stat().st_size / (1024 * 1024)
    if file_size_mb <= max_size_mb:
        return [input_path]

    doc = fitz.open(input_path)
    total = len(doc)

    # 페이지당 평균 크기로 분할 페이지 수 추정 (5MB 여유)
    effective_max = max(1, max_size_mb - 5)
    pages_per_part = max(1, int(total * effective_max / file_size_mb))

    doc.close()
    del doc
    gc.collect()
    return split_pdf_by_count(input_path, pages_per_part, output_dir, suffix="")
