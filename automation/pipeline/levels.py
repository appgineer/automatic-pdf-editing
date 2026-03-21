"""레벨 조정"""

import gc
from pathlib import Path
import fitz


def make_lut(black: int, white: int) -> bytes:
    """레벨 조정 룩업 테이블 생성"""
    black = max(0, min(255, int(black)))
    white = max(0, min(255, int(white)))
    span = max(1, white - black)
    lut = bytes([
        0 if i <= black else
        255 if i >= white else
        int((i - black) / span * 255)
        for i in range(256)
    ])
    return lut


def apply_levels_to_pdf(input_path: Path, output_path: Path, black: int, white: int) -> Path:
    """PDF 전체 페이지에 레벨 조정 적용 (PyMuPDF 픽셀 직접 조작)"""
    lut = make_lut(black, white)

    src = fitz.open(input_path)
    dst = fitz.open()

    for page_idx in range(len(src)):
        page = src[page_idx]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))

        # 픽셀 데이터에 LUT 직접 적용
        samples = bytearray(pix.samples)
        for i in range(len(samples)):
            samples[i] = lut[samples[i]]

        # 새 Pixmap 생성
        new_pix = fitz.Pixmap(pix.colorspace, pix.irect, bytes(samples), pix.alpha)

        new_page = dst.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(new_page.rect, pixmap=new_pix)

        del pix, new_pix, samples

    dst.save(str(output_path))
    dst.close()
    del dst
    src.close()
    del src
    gc.collect()
    return output_path
