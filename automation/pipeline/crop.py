"""여백 자르기: config.json의 crop_mm 대로 모든 페이지의 CropBox를 줄인다.

Acrobat의 페이지 자르기와 같은 방식이다 — 보이는 영역(CropBox)만 줄이므로
이미지 데이터는 파일에 남고 용량도 줄지 않는다. 그 대신 이미지를 다시 만들지
않아 큰 파일도 순식간에 끝나고 화질이 그대로다.

ABBYY 앞 단계에 둔다. ABBYY가 잘린 영역만 다시 저장해 용량이 줄기를 기대한다
(ABBYY가 CropBox를 무시하면 여백이 되살아날 수 있으니 결과로 확인할 것).

여백은 화면에서 본 위/아래/좌/우 기준이므로, /Rotate가 걸린 페이지도 맞도록
회전 전 좌표로 바꿔 CropBox에 넣는다 (pdf-level-preview의 _apply_page_edit와 같은 계산).

CropBox가 MediaBox 밖으로 나간 PDF(여러 프로그램을 거친 스캔)가 있다. 화면에는 겹치는 부분만 보이므로
보이는 영역(CropBox ∩ MediaBox) 기준으로 계산하고, CropBox는 MediaBox 안에 맞춰 직접 쓴다.
PyMuPDF의 set_cropbox / derotation_matrix를 그대로 쓰던 때는 이런 파일에서 "CropBox not in MediaBox"로
자르기가 통째로 건너뛰어졌고(원본 사용), 90°·270°는 나간 만큼 어긋났다.
"""

import logging
import math
import shutil
from pathlib import Path

import fitz  # PyMuPDF

from automation.models import CROP_SIDES

logger = logging.getLogger(__name__)

# 자르고 남길 최소 크기(pt). 여백이 페이지보다 크게 들어와도 페이지가 사라지지 않게 한다.
# pdf-level-preview와 같은 값.
MIN_CROP_PT = 36


def _mm_to_pt(mm: float) -> float:
    return mm * 72.0 / 25.4


def _pt_to_mm(pt: float) -> float:
    return pt * 25.4 / 72.0


def _visible_box(page) -> fitz.Rect:
    """실제로 보이는 영역 = CropBox ∩ MediaBox (page.cropbox와 같은 좌표: x는 그대로, y는 MediaBox 위에서 아래로)"""
    mb = page.mediabox  # PDF 좌표 (y 위로)
    return page.cropbox & fitz.Rect(mb.x0, 0, mb.x1, mb.y1 - mb.y0)


def _derotation(page, vb: fitz.Rect) -> fitz.Matrix:
    """화면(90° 회전 후) 좌표 → 회전 전 좌표. page.derotation_matrix와 같은 식을 보이는 영역 vb 크기로 만든다
    (page.derotation_matrix는 CropBox 크기로 만들어 CropBox가 MediaBox 밖으로 나간 파일에서 어긋난다)"""
    w, h = vb.width, vb.height
    rot = {0: (1, 0, 0, 1, 0, 0), 90: (0, 1, -1, 0, h, 0),
           180: (-1, 0, 0, -1, w, h), 270: (0, -1, 1, 0, 0, w)}[page.rotation % 360]
    return ~fitz.Matrix(*rot)


def _set_cropbox(page, box: fitz.Rect):
    """CropBox를 넣는다. box는 page.cropbox와 같은 좌표.

    PyMuPDF set_cropbox는 PDF 좌표로 바꾼 값이 소수점 오차로라도 MediaBox를 벗어나면 막는다. 직접 PDF 좌표로 바꿔
    MediaBox 안으로 맞추고, 소수 넷째 자리에서 안쪽으로 반올림해 쓴다 (0.0001pt 줄어드는 것은 보이지 않는다)
    """
    mb = page.mediabox
    x0, x1 = max(box.x0, mb.x0), min(box.x1, mb.x1)
    y0, y1 = max(mb.y1 - box.y1, mb.y0), min(mb.y1 - box.y0, mb.y1)
    x0, y0 = math.ceil(x0 * 1e4) / 1e4, math.ceil(y0 * 1e4) / 1e4
    x1, y1 = math.floor(x1 * 1e4) / 1e4, math.floor(y1 * 1e4) / 1e4
    page.parent.xref_set_key(page.xref, "CropBox", f"[{x0:.4f} {y0:.4f} {x1:.4f} {y1:.4f}]")


def _clamp(margins: list, w: float, h: float) -> list:
    """여백 [위, 아래, 좌, 우](pt)를 w×h 페이지 안에 가둔다. 남는 크기는 MIN_CROP_PT 이상"""
    out = list(margins)
    for a, b, span in ((0, 1, h), (2, 3, w)):
        room = max(0.0, span - MIN_CROP_PT)
        if out[a] + out[b] > room:
            # 두 쪽 비율을 유지한 채 함께 줄인다
            total = out[a] + out[b]
            out[a] = room * out[a] / total
            out[b] = room * out[b] / total
    return out


def _save(doc, output_path: Path):
    """증분 저장(뒤에 덧붙이기)으로 끝낸다. 100MB짜리를 통째로 다시 쓰지 않아 몇 초면 된다.

    손상됐다가 복구된 PDF 등 증분 저장이 안 되는 파일은 통째로 다시 쓴다.
    """
    try:
        doc.save(output_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        return
    except Exception as e:
        logger.info(f"증분 저장 불가 — 통째로 다시 씀: {output_path.name} ({e})")
    full = output_path.with_name(output_path.stem + "_full.pdf")
    doc.save(full)
    doc.close()
    full.replace(output_path)


def crop_pdf(input_path: Path, output_path: Path, crop_mm: dict) -> bool:
    """모든 페이지를 crop_mm(mm) 만큼 가린 PDF를 output_path에 만든다.

    잘라낼 값이 없거나 실패하면 False를 반환해 호출부가 원본을 그대로 쓰게 한다.
    """
    margins_mm = [float(crop_mm.get(s, 0) or 0) for s in CROP_SIDES]
    if not any(m > 0 for m in margins_mm):
        return False  # 자르기 설정 없음 — 건너뜀

    top, bottom, left, right = (_mm_to_pt(m) for m in margins_mm)

    # 통째로 다시 쓰지 않고 뒤에 덧붙이는 증분 저장을 쓰려면 사본에서 작업해야 한다
    try:
        shutil.copy2(str(input_path), str(output_path))
        doc = fitz.open(output_path)
    except Exception as e:
        logger.error(f"여백 자르기 준비 실패 — 자르지 않음: {input_path.name} ({e})")
        return False

    try:
        before = None
        for page in doc:
            r = page.rect  # 화면 기준 (회전 반영)
            t, b, l, rt = _clamp([top, bottom, left, right], r.width, r.height)
            vis = fitz.Rect(r.x0 + l, r.y0 + t, r.x1 - rt, r.y1 - b)
            # 화면 좌표 → 회전 전 좌표. 결과는 보이는 영역 왼쪽 위 기준이라 그만큼 옮긴다
            crop = _visible_box(page)
            box = (vis * _derotation(page, crop)).normalize()
            box = fitz.Rect(box.x0 + crop.x0, box.y0 + crop.y0,
                            box.x1 + crop.x0, box.y1 + crop.y0)
            if before is None:
                before = (r.width, r.height)
            _set_cropbox(page, box & crop)
        after = doc[0].rect if doc.page_count else None
        _save(doc, output_path)
    except Exception as e:
        logger.error(f"여백 자르기 실패 — 원본 사용: {input_path.name} ({e})")
        doc.close()
        output_path.unlink(missing_ok=True)
        return False
    finally:
        if not doc.is_closed:
            doc.close()

    if before and after:
        logger.info(
            f"여백 자르기: 위 {margins_mm[0]:g} 아래 {margins_mm[1]:g} "
            f"좌 {margins_mm[2]:g} 우 {margins_mm[3]:g} (mm) — 1쪽 "
            f"{_pt_to_mm(before[0]):.1f}×{_pt_to_mm(before[1]):.1f} → "
            f"{_pt_to_mm(after.width):.1f}×{_pt_to_mm(after.height):.1f} mm"
        )
    return True
