"""레벨 조정 (멀티프로세싱)"""

import gc
import os
import tempfile
from multiprocessing import Pool, cpu_count
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


def _process_page(args):
    """단일 페이지 처리 (멀티프로세싱용)"""
    input_path, page_idx, tmp_dir, scale, black, white = args

    src = fitz.open(input_path)
    page = src[page_idx]
    page_width = page.rect.width
    page_height = page.rect.height

    # 페이지 → 600 DPI로 렌더링
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
    tmp_png = os.path.join(tmp_dir, f"_page_{page_idx}.png")
    pix.save(tmp_png)
    del pix
    src.close()

    # PIL로 열어서 레벨 조정 후 JPEG 2000 고품질 손실 압축으로 저장
    img = Image.open(tmp_png)
    img = apply_levels(img, black, white)
    os.remove(tmp_png)
    tmp_jp2 = os.path.join(tmp_dir, f"_page_{page_idx}.jp2")
    img.save(tmp_jp2, format='JPEG2000', irreversible=True,
             quality_mode='dB', quality_layers=[30])
    del img

    return (page_idx, tmp_jp2, page_width, page_height)


def apply_levels_to_pdf(input_path: Path, output_path: Path, black: int, white: int) -> Path:
    """PDF 전체 페이지에 레벨 조정 적용 (600 DPI, 멀티프로세싱)"""
    DPI = 600
    scale = DPI / 72

    src = fitz.open(input_path)
    total_pages = len(src)
    src.close()

    tmp_dir = tempfile.mkdtemp()
    workers = max(1, cpu_count() - 1)

    try:
        # 멀티프로세싱으로 전체 페이지 병렬 처리
        tasks = [
            (str(input_path), page_idx, tmp_dir, scale, black, white)
            for page_idx in range(total_pages)
        ]

        with Pool(processes=workers) as pool:
            results = pool.map(_process_page, tasks)

        # 페이지 순서대로 정렬
        results.sort(key=lambda x: x[0])

        # PDF 조립 (메인 프로세스에서 순차 수행)
        dst = fitz.open()
        for page_idx, jp2_path, page_width, page_height in results:
            new_page = dst.new_page(width=page_width, height=page_height)
            new_page.insert_image(new_page.rect, filename=jp2_path)
            os.remove(jp2_path)

        dst.save(str(output_path), garbage=4, deflate=True)
        dst.close()
        del dst
    finally:
        # 임시 폴더 정리
        try:
            os.rmdir(tmp_dir)
        except OSError:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
        gc.collect()

    return output_path
