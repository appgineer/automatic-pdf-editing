"""레벨 조정"""

import gc
import io
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
    """PDF 내 이미지를 직접 추출하여 레벨 조정 적용 (원본 해상도 유지)"""
    doc = fitz.open(input_path)

    try:
        xrefs_done = set()
        for page in doc:
            for img_info in page.get_images():
                xref = img_info[0]
                if xref in xrefs_done:
                    continue
                xrefs_done.add(xref)

                # 원본 이미지 추출
                img_dict = doc.extract_image(xref)
                pil_img = Image.open(io.BytesIO(img_dict["image"]))

                # CMYK → RGB 변환
                if pil_img.mode == "CMYK":
                    pil_img = pil_img.convert("RGB")
                elif pil_img.mode not in ("RGB", "L"):
                    pil_img = pil_img.convert("RGB")

                # 레벨 조정
                pil_img = apply_levels(pil_img, black, white)

                # 원본 포맷으로 바이트 변환
                buf = io.BytesIO()
                ext = img_dict["ext"]
                if ext in ("jpeg", "jpg"):
                    pil_img.save(buf, format="JPEG", quality=95)
                else:
                    pil_img.save(buf, format="PNG")

                # 이미지 교체
                page.replace_image(xref, stream=buf.getvalue())
                del pil_img, buf

        doc.save(str(output_path))
    finally:
        doc.close()
        del doc
        gc.collect()

    return output_path
