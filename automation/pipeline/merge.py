"""PDF 합치기"""

from pathlib import Path
import fitz


def merge_pdfs(pdf_files: list[Path], output_path: Path) -> Path:
    """여러 PDF를 하나로 합침. 1개면 그대로 복사."""
    if len(pdf_files) == 1:
        if pdf_files[0] != output_path:
            import shutil
            shutil.copy2(pdf_files[0], output_path)
        return output_path

    merged = fitz.open()
    for pdf_file in pdf_files:
        doc = fitz.open(pdf_file)
        merged.insert_pdf(doc)
        doc.close()
    merged.save(str(output_path))
    merged.close()
    return output_path
