"""임시 테스트 스크립트 (Windows): 폴더 안 PDF들을 PyMuPDF 코덱 변환.

실제 파이프라인과 동일한 automation/pipeline/recompress.compress_pdf 를 그대로 재사용한다.
JPEG2000 → JPEG(baseline 4:2:0)로만 바꾸고(JBIG2 등 흑백은 유지),
빈 페이지가 생기면 실패로 표시한다.

사용법 (레포 루트에서):
    python codec_test.py "C:\\경로\\폴더"
    - 폴더를 스크립트 위로 드래그&드롭 해도 됨
    - 인자를 안 주면 아래 FOLDER 값, 그것도 비면 스크립트가 있는 폴더를 사용

결과: 같은 폴더에 '원본이름_코덱.pdf' 생성 (이미 _코덱 붙은 파일은 건너뜀).
"""

import sys
import time
import logging
from pathlib import Path
from collections import Counter

import fitz  # PyMuPDF

# 실제 코덱 변환 함수 재사용
sys.path.insert(0, str(Path(__file__).resolve().parent))
from automation.pipeline.recompress import compress_pdf, JPEG_QUALITY

# 인자를 안 줄 때 사용할 폴더 (여기에 경로를 직접 적어도 됨)
FOLDER = r""

SUFFIX = "_코덱"

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def codec_dist(path: Path) -> dict:
    d = fitz.open(path)
    c = Counter()
    for i in range(d.page_count):
        for im in d[i].get_images(full=True):
            f = d.xref_get_key(im[0], "Filter")
            c[f[1] if f and f[0] != "null" else "none"] += 1
    d.close()
    return dict(c)


def image_counts(path: Path) -> list:
    d = fitz.open(path)
    counts = [len(d[i].get_images()) for i in range(d.page_count)]
    d.close()
    return counts


def main():
    if len(sys.argv) > 1:
        folder = Path(sys.argv[1])
    elif FOLDER:
        folder = Path(FOLDER)
    else:
        folder = Path(__file__).resolve().parent

    if not folder.is_dir():
        print(f"폴더를 찾을 수 없음: {folder}")
        return

    pdfs = [p for p in sorted(folder.glob("*.pdf")) if not p.stem.endswith(SUFFIX)]
    if not pdfs:
        print(f"처리할 PDF가 없음: {folder}")
        return

    print(f"대상 폴더: {folder}")
    print(f"품질(JPEG_QUALITY): {JPEG_QUALITY}")
    print(f"처리할 PDF: {len(pdfs)}개  (큰 파일은 시간이 걸립니다)\n")

    start = time.time()
    for src in pdfs:
        out = src.with_name(f"{src.stem}{SUFFIX}.pdf")
        print("=" * 64)
        print(f"입력: {src.name}  ({src.stat().st_size / 1e6:.0f}MB)")

        before = image_counts(src)
        before_codec = codec_dist(src)

        print("  변환 중... (JPEG2000 재인코딩+저장, 완료까지 수 분 걸릴 수 있음)", flush=True)
        ok = compress_pdf(src, out)
        if not ok:
            print("결과: 실패 → 원본 폴백 대상 (빈 페이지 감지 또는 오류). 위 로그 확인.")
            continue

        after = image_counts(out)
        blanks = [i for i in range(len(before))
                  if before[i] > 0 and (i >= len(after) or after[i] == 0)]
        print(f"출력: {out.name}  ({out.stat().st_size / 1e6:.0f}MB)")
        print(f"페이지수: {len(before)} -> {len(after)}")
        print(f"빈 페이지: {blanks if blanks else '없음'}")
        print(f"코덱 전: {before_codec}")
        print(f"코덱 후: {codec_dist(out)}   (JPXDecode 사라지면 성공)")

    print("=" * 64)
    print("완료.")
    elapsed = time.time() - start
    print(f"소요 시간: {int(elapsed // 60)}분 {int(elapsed % 60)}초")


if __name__ == "__main__":
    main()
    input("\n엔터를 누르면 종료합니다...")
