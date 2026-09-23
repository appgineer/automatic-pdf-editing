"""여백 자르기: config.json의 crop_mm 대로 모든 페이지의 CropBox를 줄인다.

Acrobat의 페이지 자르기와 같은 방식이다 — 보이는 영역(CropBox)만 줄이므로
이미지 데이터는 파일에 남고 용량도 줄지 않는다. 그 대신 이미지를 다시 만들지
않아 큰 파일도 순식간에 끝나고 화질이 그대로다.

ABBYY 다음 단계에 둔다. 앞에 두면 ABBYY가 가려 둔 여백을 되살릴 수 있다.

여백은 화면에서 본 위/아래/좌/우 기준이므로, /Rotate가 걸린 페이지도 맞도록
derotation_matrix로 회전 전 좌표로 바꿔 CropBox에 넣는다
(pdf-level-preview의 _apply_page_edit와 같은 계산).
"""

import logging
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
            # 화면 좌표 → 회전 전 좌표. 결과는 현재 CropBox 왼쪽 위 기준이라 그만큼 옮긴다
            box = (vis * page.derotation_matrix).normalize()
            crop = page.cropbox
            box = fitz.Rect(box.x0 + crop.x0, box.y0 + crop.y0,
                            box.x1 + crop.x0, box.y1 + crop.y0)
            if before is None:
                before = (r.width, r.height)
            page.set_cropbox(box & crop)
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
