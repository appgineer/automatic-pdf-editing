"""Ghostscript 이미지 재압축 (아이패드 렉 방지)"""

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# QFactor 3.0 DCT 재인코딩 (다운샘플 없음, 색공간 유지) — 사용자 검증 명령
_DISTILLER = (
    "<< /ColorImageDict << /QFactor 3.0 /Blend 1 "
    "/HSamples [2 1 1 2] /VSamples [2 1 1 2] >> "
    "/GrayImageDict << /QFactor 3.0 /Blend 1 "
    "/HSamples [2 1 1 2] /VSamples [2 1 1 2] >> >> setdistillerparams"
)


def _find_ghostscript() -> str | None:
    """gswin64c(Windows) / gs(mac,linux) 실행파일 탐색"""
    for name in ("gswin64c", "gswin32c", "gs"):
        found = shutil.which(name)
        if found:
            return found
    # PATH에 없으면 기본 설치 경로 탐색 (Windows)
    for base in (r"C:\Program Files\gs", r"C:\Program Files (x86)\gs"):
        for exe in Path(base).glob("gs*/bin/gswin*c.exe"):
            return str(exe)
    return None


def compress_pdf(input_path: Path, output_path: Path, timeout: int = 3600) -> bool:
    """Ghostscript로 이미지 재압축. 성공 시 output_path 생성하고 True 반환."""
    gs = _find_ghostscript()
    if not gs:
        logger.error("Ghostscript(gswin64c) 미설치 — 압축 건너뜀")
        return False

    args = [
        gs,
        "-o", str(output_path),
        "-sDEVICE=pdfwrite",
        "-dPassThroughJPXImages=false",
        "-dAutoFilterColorImages=false",
        "-dAutoFilterGrayImages=false",
        "-dEncodeColorImages=true",
        "-dEncodeGrayImages=true",
        "-dColorImageFilter=/DCTEncode",
        "-dGrayImageFilter=/DCTEncode",
        "-dDownsampleColorImages=false",
        "-dDownsampleGrayImages=false",
        "-dColorConversionStrategy=/LeaveColorUnchanged",
        "-c", _DISTILLER,
        "-f", str(input_path),
    ]

    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        logger.error(f"Ghostscript 시간초과: {input_path.name}")
        return False

    if result.returncode != 0:
        logger.error(f"Ghostscript 실패 (code {result.returncode}): {result.stderr[-500:]}")
        return False

    if not output_path.exists() or output_path.stat().st_size == 0:
        logger.error(f"Ghostscript 출력 없음: {output_path.name}")
        return False

    return True
