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
        part_doc.save(str(out_path), garbage=4, deflate=True)
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
    total = len(doc)
    stem = input_path.stem
    results = []

    ranges = [r.strip() for r in ranges_str.split(",") if r.strip()]
    for idx, page_range in enumerate(ranges, 1):
        parts = page_range.split("-")
        start = int(parts[0]) - 1  # 0-indexed
        end = int(parts[1]) if len(parts) > 1 else int(parts[0])

        # 시작점이 총 페이지 이상이면 건너뛰기
        if start >= total:
            continue
        # 끝점이 총 페이지를 넘으면 총 페이지까지만
        end = min(end, total)

        part_doc = fitz.open()
        part_doc.insert_pdf(doc, from_page=start, to_page=end - 1)

        out_name = f"{stem}{idx}.pdf"
        out_path = output_dir / out_name
        part_doc.save(str(out_path), garbage=4, deflate=True)
        part_doc.close()
        del part_doc
        results.append(out_path)

    doc.close()
    del doc
    gc.collect()
    return results


def split_pdf_by_size(input_path: Path, max_size_mb: int, output_dir: Path) -> list[Path]:
    """파일 크기 기준 분할 (페이지별 개별 측정 후 누적)"""
    if max_size_mb <= 0:
        return [input_path]

    max_size = max_size_mb * 1024 * 1024
    if input_path.stat().st_size <= max_size:
        return [input_path]

    doc = fitz.open(input_path)
    total = len(doc)

    # 1단계: 각 페이지 크기 개별 측정
    page_sizes = []
    for i in range(total):
        tmp_doc = fitz.open()
        tmp_doc.insert_pdf(doc, from_page=i, to_page=i)
        page_sizes.append(len(tmp_doc.tobytes(garbage=4, deflate=True)))
        tmp_doc.close()
        del tmp_doc

    # 2단계: 누적 합산으로 분할 지점 결정
    stem = input_path.stem
    results = []
    part = 1
    start = 0

    while start < total:
        current_size = 0
        end = start
        while end < total:
            if current_size + page_sizes[end] > max_size and end > start:
                break
            current_size += page_sizes[end]
            end += 1

        part_doc = fitz.open()
        part_doc.insert_pdf(doc, from_page=start, to_page=end - 1)
        out_path = output_dir / f"{stem}{part}.pdf"
        part_doc.save(str(out_path), garbage=4, deflate=True)
        part_doc.close()
        del part_doc
        results.append(out_path)

        start = end
        part += 1

    doc.close()
    del doc
    gc.collect()
    return results
