"""이미지 재압축: JPEG2000 → JPEG 코덱 변환 (아이패드 렉 방지)

ABBYY 고급 출력물은 이미지가 JPEG2000(JPX)으로 인코딩되는데,
아이패드에서 JPEG2000 디코딩이 무거워 렉이 생긴다.
PyMuPDF(MuPDF)로 lossy 이미지(JPEG2000/JPEG)만 JPEG로 재인코딩한다.
흑백 텍스트(JBIG2 등 bitonal)는 손대지 않아 선명도를 유지한다.

(이전에는 Ghostscript로 처리했으나, GS의 JPEG2000/JBIG2 디코더가 일부
이미지를 조용히 드롭해 중간중간 빈 페이지가 생기는 문제가 있어 교체함.)
"""

import logging
from pathlib import Path

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# JPEG 재인코딩 품질 (1~100). 높을수록 고화질/대용량. 용량이 크면 낮추거나 DOWNSAMPLE 사용.
JPEG_QUALITY = 85

# 용량이 과도하면 True로 켜서 해상도를 낮춘다 (열람용 화질 유지, 용량 대폭 감소).
DOWNSAMPLE = False
DPI_THRESHOLD = 200  # 이 DPI를 넘는 이미지만 다운샘플 대상
DPI_TARGET = 150     # 낮출 목표 DPI


def compress_pdf(input_path: Path, output_path: Path) -> bool:
    """JPEG2000 등 lossy 이미지를 JPEG로 재인코딩. 성공 시 output_path 생성하고 True 반환.

    변환 후 이미지가 사라져 빈 페이지가 생기면 False를 반환하여
    호출부가 원본을 그대로 사용(폴백)하도록 한다.
    """
    try:
        doc = fitz.open(input_path)
    except Exception as e:
        logger.error(f"PDF 열기 실패 — 재압축 건너뜀: {input_path.name} ({e})")
        return False

    # 변환 전 페이지별 이미지 개수 (빈 페이지 검증용)
    before = [len(doc[i].get_images()) for i in range(doc.page_count)]

    kwargs = dict(quality=JPEG_QUALITY, lossy=True, lossless=False, bitonal=False)
    if DOWNSAMPLE:
        kwargs.update(dpi_threshold=DPI_THRESHOLD, dpi_target=DPI_TARGET)

    try:
        doc.rewrite_images(**kwargs)
    except Exception as e:
        logger.error(f"이미지 재압축 실패: {input_path.name} ({e})")
        doc.close()
        return False

    # 검증: 이미지가 있던 페이지가 이미지 0개가 되면 빈 페이지 → 실패 처리(원본 폴백)
    for i in range(doc.page_count):
        if before[i] > 0 and len(doc[i].get_images()) == 0:
            logger.error(f"재압축 후 빈 페이지 발생(p{i}) — 원본 사용: {input_path.name}")
            doc.close()
            return False

    try:
        doc.save(output_path, garbage=4, deflate=True)
    finally:
        doc.close()

    if not output_path.exists() or output_path.stat().st_size == 0:
        logger.error(f"재압축 출력 없음: {output_path.name}")
        return False

    return True
