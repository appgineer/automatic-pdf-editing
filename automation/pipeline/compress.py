"""ZIP 압축"""

import zipfile
from pathlib import Path


def create_customer_zip(customer_name: str, files: list[Path], output_dir: Path) -> Path:
    """고객의 모든 완료 파일을 ZIP으로 압축"""
    zip_name = f"{customer_name} 님.zip"
    zip_path = output_dir / zip_name

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in files:
            zf.write(file_path, file_path.name)

    return zip_path
