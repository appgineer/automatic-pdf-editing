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
    channels = len(image.getbands())
    return image.point(lut * channels)


def apply_levels_to_pdf(input_path: Path, output_path: Path, black: int, white: int) -> Path:
    """PDF 전체 페이지에 레벨 조정 적용 (600 DPI)"""
    DPI = 600
    scale = DPI / 72

    src = fitz.open(input_path)
    dst = fitz.open()
    tmp_dir = tempfile.mkdtemp()

    try:
        for page_idx in range(len(src)):
            page = src[page_idx]

            # 페이지 → 600 DPI로 렌더링
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
            tmp_png = os.path.join(tmp_dir, f"_page_{page_idx}.png")
            pix.save(tmp_png)
            del pix

            # PIL로 열어서 레벨 조정 후 JPEG 2000 고품질 손실 압축으로 저장
            img = Image.open(tmp_png)
            img = apply_levels(img, black, white)
            os.remove(tmp_png)
            tmp_jp2 = os.path.join(tmp_dir, f"_page_{page_idx}.jp2")
            img.save(tmp_jp2, format='JPEG2000', irreversible=True,
                     quality_mode='dB', quality_layers=[30])
            del img

            # PDF 페이지에 삽입
            new_page = dst.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(new_page.rect, filename=tmp_jp2)

            os.remove(tmp_jp2)

        dst.save(str(output_path), garbage=4, deflate=True)
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
