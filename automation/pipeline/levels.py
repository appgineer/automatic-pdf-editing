"""레벨 조정 (main.py의 apply_levels 재사용)"""

import gc
from pathlib import Path
from PIL import Image
import fitz


def apply_levels(image: Image.Image, black: int, white: int) -> Image.Image:
    """이미지에 레벨 조정 적용"""
    black = max(0, min(255, int(black)))
    white = max(0, min(255, int(white)))
    span = max(1, white - black)
    lut = [
        0 if i <= black else
        255 if i >= white else
        int((i - black) / span * 255)
        for i in range(256)
    ]
    return image.point(lut * 3)


def apply_levels_to_pdf(input_path: Path, output_path: Path, black: int, white: int) -> Path:
    """PDF 전체 페이지에 레벨 조정 적용"""
    src = fitz.open(input_path)
    dst = fitz.open()

    for page_idx in range(len(src)):
        page = src[page_idx]
        # 페이지를 이미지로 렌더링 (300 DPI)
        mat = fitz.Matrix(300 / 72, 300 / 72)
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        del pix

        # 레벨 조정
        img = apply_levels(img, black, white)

        # 이미지를 PDF 페이지로 변환
        img_bytes = img.tobytes("raw", "RGB")
        new_pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, img.width, img.height), img_bytes, False)

        new_page = dst.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(new_page.rect, pixmap=new_pix)
        del new_pix, img, img_bytes

    dst.save(str(output_path))
    dst.close()
    del dst
    src.close()
    del src
    gc.collect()
    return output_path
