"""이미지 재압축: JPEG2000 → JPEG 코덱 변환 (아이패드 렉 방지)

ABBYY 고급 출력물은 이미지가 JPEG2000(JPX)으로 인코딩되는데,
아이패드에서 JPEG2000 디코딩이 무거워 렉이 생긴다.
PyMuPDF(MuPDF)로 JPEG2000 이미지만 골라 JPEG(DCTDecode)로 재인코딩한다.
흑백 텍스트(JBIG2 등)나 이미 JPEG인 이미지는 손대지 않는다.

주의:
- rewrite_images()는 JPEG2000을 JPEG로 바꾸지 않고 그대로 재압축만 하므로 렉이 안 풀린다.
  그래서 이미지 스트림을 직접 JPEG으로 교체(update_stream)한다.
- 새 이미지를 추가(replace_image)하면 페이지에 이미지가 중복되어 용량 2배 + 렉 악화 →
  반드시 같은 xref를 '제자리 교체'한다.
- 이전에는 Ghostscript로 처리했으나, GS의 JPEG2000/JBIG2 디코더가 일부 이미지를
  조용히 드롭해 중간중간 빈 페이지가 생기는 문제가 있어 교체함.
"""

import io
import logging
import time
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

logger = logging.getLogger(__name__)

# JPEG 재인코딩 품질 (1~100). 높을수록 고화질/대용량.
# 600 DPI 유지(다운샘플 없음) + baseline 4:2:0 기준 100p 실측:
#   q40≈74MB, q50≈83MB, q60≈91MB, q80≈127MB (800p는 약 8배). ABBYY 원본(JPEG2000)은 63MB.
#   GS(QFactor 3.0)와 비슷한 용량대 = q40~50.
JPEG_QUALITY = 50

# 용량이 과도하면 True로 켜서 해상도를 낮춘다 (열람용 화질 유지, 용량 감소).
DOWNSAMPLE = False
DPI_TARGET = 150  # 다운샘플 목표 DPI (2의 배수로만 축소되므로 근사치)

# 진행 보고 최소 간격(초). 호출부가 보고마다 작업 목록 트리를 통째로 다시 그리므로
# 페이지마다 그대로 흘리면 낭비다.
STEP_REPORT_INTERVAL = 1.0


def _to_jpeg_pixmap(doc: fitz.Document, xref: int):
    """xref 이미지를 JPEG로 넣기 좋은 Pixmap(회색 or RGB, 알파 없음)으로 디코딩."""
    pix = fitz.Pixmap(doc, xref)
    if pix.alpha:
        pix = fitz.Pixmap(pix, 0)  # 알파 제거
    if pix.colorspace is None or pix.colorspace.n not in (1, 3):
        pix = fitz.Pixmap(fitz.csRGB, pix)  # CMYK 등 → RGB
    return pix


def _maybe_downsample(pix, page, xref):
    """DOWNSAMPLE가 켜져 있고 이미지 DPI가 목표보다 높으면 2의 배수로 축소."""
    rects = page.get_image_rects(xref)
    if not rects:
        return pix
    disp_w_in = max(r.width for r in rects) / 72.0
    if disp_w_in <= 0:
        return pix
    dpi = pix.width / disp_w_in
    factor, d = 0, dpi
    while d / 2 >= DPI_TARGET:
        factor += 1
        d /= 2
    if factor:
        pix.shrink(factor)
    return pix


def compress_pdf(input_path: Path, output_path: Path, on_step=None) -> bool:
    """JPEG2000 이미지를 JPEG로 재인코딩. 성공 시 output_path 생성하고 True 반환.

    변환 후 이미지가 사라져 빈 페이지가 생기면 False를 반환하여
    호출부가 원본을 그대로 사용(폴백)하도록 한다.

    on_step(text)을 주면 진행 상황을 보고한다. 이 단계는 오래 걸리는데 중간 신호가
    없어 멈춘 건지 처리 중인지 구분할 수 없었다. 마지막 저장은 페이지 단위 신호가
    없으므로 별도 문구로 알린다 — 안 그러면 카운터가 끝까지 찬 채로 멈춰 있어
    마지막 페이지에서 멈춘 것과 구분되지 않는다.
    """
    last_report = 0.0

    def report(text: str, force: bool = False):
        nonlocal last_report
        if on_step is None:
            return
        now = time.time()
        if force or now - last_report >= STEP_REPORT_INTERVAL:
            last_report = now
            on_step(text)

    try:
        doc = fitz.open(input_path)
    except Exception as e:
        logger.error(f"PDF 열기 실패 — 재압축 건너뜀: {input_path.name} ({e})")
        return False

    # 변환 전 페이지별 이미지 개수 (빈 페이지 검증용)
    before = [len(doc[i].get_images()) for i in range(doc.page_count)]

    seen: set[int] = set()
    try:
        for pno in range(doc.page_count):
            report(f"이미지 재압축 ({pno + 1}/{doc.page_count}p)", force=(pno == 0))
            page = doc[pno]
            for img in page.get_images(full=True):
                xref = img[0]
                if xref in seen:
                    continue
                seen.add(xref)

                filt = doc.xref_get_key(xref, "Filter")
                if not (filt and "JPX" in str(filt[1])):
                    continue  # JPEG2000만 변환, 나머지(JBIG2/기존 JPEG 등)는 유지

                pix = _to_jpeg_pixmap(doc, xref)
                if DOWNSAMPLE:
                    pix = _maybe_downsample(pix, page, xref)

                cs = "/DeviceGray" if pix.colorspace.n == 1 else "/DeviceRGB"
                w, h = pix.width, pix.height
                # baseline + 4:2:0 JPEG으로 인코딩 (아이패드 디코딩이 빠름, GS와 동일 방식).
                # MuPDF의 tobytes("jpeg")는 progressive + 4:4:4라 태블릿에서 렉이 더 걸려
                # Pillow로 인코딩한다. 4:2:0는 밝기(글자 선명도)는 풀해상도 유지, 색차만 절반.
                mode = "L" if pix.colorspace.n == 1 else "RGB"
                img = Image.frombytes(mode, (w, h), pix.samples)
                pix = None
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=JPEG_QUALITY,
                         subsampling=2, progressive=False, optimize=True)
                jpg = buf.getvalue()

                # 같은 xref 스트림을 raw JPEG으로 제자리 교체 (compress=False = 재압축 안 함)
                doc.update_stream(xref, jpg, compress=False)
                doc.xref_set_key(xref, "Filter", "/DCTDecode")
                doc.xref_set_key(xref, "ColorSpace", cs)
                doc.xref_set_key(xref, "BitsPerComponent", "8")
                doc.xref_set_key(xref, "Width", str(w))
                doc.xref_set_key(xref, "Height", str(h))
                doc.xref_set_key(xref, "DecodeParms", "null")  # JPX용 파라미터 제거
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

    report("이미지 재압축 저장중", force=True)
    try:
        doc.save(output_path, garbage=4, deflate=True)
    finally:
        doc.close()

    if not output_path.exists() or output_path.stat().st_size == 0:
        logger.error(f"재압축 출력 없음: {output_path.name}")
        return False

    return True
