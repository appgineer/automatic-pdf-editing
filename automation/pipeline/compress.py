"""ZIP 압축"""

import zipfile
from pathlib import Path

SIZE_LIMIT = 1_900_000_000  # 1.9GB


def create_customer_zip(customer_name: str, customer_dir: Path, output_dir: Path) -> list[Path]:
    """고객 폴더 직속 PDF들을 1.9GB 단위로 묶어 ZIP 생성 (고객/파일.pdf 구조)."""
    files = sorted(f for f in customer_dir.glob("*.pdf") if f.is_file())
    if not files:
        return []

    # 파일 단위로 1.9GB 그룹핑
    groups: list[list[Path]] = []
    current_group: list[Path] = []
    current_size = 0

    for f in files:
        fsize = f.stat().st_size
        if current_group and current_size + fsize > SIZE_LIMIT:
            groups.append(current_group)
            current_group = [f]
            current_size = fsize
        else:
            current_group.append(f)
            current_size += fsize
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
            for f in group:
                zf.write(f, f"{customer_name}/{f.name}")
        zip_paths.append(zip_path)

    return zip_paths
