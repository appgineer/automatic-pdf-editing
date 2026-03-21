"""레벨 조정"""

import gc
import os
import tempfile
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
    tmp_dir = tempfile.mkdtemp()

    try:
        for page_idx in range(len(src)):
            page = src[page_idx]

            # 페이지 → 임시 PNG 파일로 저장
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            tmp_png = os.path.join(tmp_dir, f"_page_{page_idx}.png")
            pix.save(tmp_png)
            del pix

            # PIL로 열어서 레벨 조정 후 다시 저장
            img = Image.open(tmp_png)
            img = apply_levels(img, black, white)
            img.save(tmp_png)
            del img

            # PDF 페이지에 삽입
            new_page = dst.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(new_page.rect, filename=tmp_png)

            os.remove(tmp_png)

        dst.save(str(output_path))
    finally:
        dst.close()
        del dst
        src.close()
        del src
        # 임시 폴더 정리
        try:
            os.rmdir(tmp_dir)
        except OSError:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
        gc.collect()

    return output_path
