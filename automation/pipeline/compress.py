"""ZIP 압축"""

import zipfile
from pathlib import Path

SIZE_LIMIT = 1_900_000_000  # 1.9GB


def _book_size(book_dir: Path) -> int:
    return sum(f.stat().st_size for f in book_dir.rglob("*") if f.is_file())


def create_customer_zip(customer_name: str, customer_dir: Path, output_dir: Path) -> list[Path]:
    """고객 폴더 안의 책별 서브폴더를 책 단위로 묶어 ZIP 생성.

    한 책이 단독으로 1.9GB를 넘으면 그 책만 단독 ZIP으로 묶음
    (한 책이 두 ZIP으로 갈리지 않음).
    """
    book_dirs = sorted(d for d in customer_dir.iterdir() if d.is_dir())
    if not book_dirs:
        return []

    # 책 단위로 1.9GB 그룹핑
    groups: list[list[Path]] = []
    current_group: list[Path] = []
    current_size = 0

    for book_dir in book_dirs:
        bsize = _book_size(book_dir)
        if current_group and current_size + bsize > SIZE_LIMIT:
            groups.append(current_group)
            current_group = [book_dir]
            current_size = bsize
        else:
            current_group.append(book_dir)
            current_size += bsize
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
            for book_dir in group:
                for file_path in sorted(book_dir.rglob("*")):
                    if not file_path.is_file():
                        continue
                    rel = file_path.relative_to(customer_dir)
                    arcname = f"{customer_name}/{rel.as_posix()}"
                    zf.write(file_path, arcname)
        zip_paths.append(zip_path)

    return zip_paths
