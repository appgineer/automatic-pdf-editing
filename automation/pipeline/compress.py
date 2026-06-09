"""ZIP 압축"""

import zipfile
from pathlib import Path

SIZE_LIMIT = 1_900_000_000  # 1.9GB


def create_customer_zip(customer_name: str, customer_dir: Path, output_dir: Path) -> list[Path]:
    """고객 폴더 안의 책들을 1.9GB 단위로 묶어 ZIP 생성.

    평탄 PDF는 책 1권, 책 하위폴더(쪼개진 파트들)도 책 1권으로 보고
    책 단위로 그룹핑한다(한 책이 두 ZIP으로 갈리지 않음).
    arcname은 고객 폴더 기준 상대경로 → 폴더 책은 `고객/책/책_1.pdf`, 평탄 책은 `고객/책.pdf`.
    """
    # 책 단위 항목 수집 (item = 한 책에 속한 파일 리스트)
    items: list[list[Path]] = []
    for entry in sorted(customer_dir.iterdir()):
        if entry.is_file() and entry.suffix.lower() == ".pdf":
            items.append([entry])
        elif entry.is_dir():
            book_files = sorted(f for f in entry.rglob("*.pdf") if f.is_file())
            if book_files:
                items.append(book_files)
    if not items:
        return []

    # 책 단위로 1.9GB 그룹핑
    groups: list[list[list[Path]]] = []
    current_group: list[list[Path]] = []
    current_size = 0

    for item in items:
        isize = sum(f.stat().st_size for f in item)
        if current_group and current_size + isize > SIZE_LIMIT:
            groups.append(current_group)
            current_group = [item]
            current_size = isize
        else:
            current_group.append(item)
            current_size += isize
    if current_group:
        groups.append(current_group)

    # 그룹별 ZIP 생성
    zip_paths: list[Path] = []
    for i, group in enumerate(groups):
        if len(groups) == 1:
            zip_name = f"{customer_name}님.zip"
        else:
            zip_name = f"{customer_name}님_{i + 1}.zip"
        zip_path = output_dir / zip_name

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for item in group:
                for f in item:
                    rel = f.relative_to(customer_dir)
                    zf.write(f, f"{customer_name}/{rel.as_posix()}")
        zip_paths.append(zip_path)

    return zip_paths
