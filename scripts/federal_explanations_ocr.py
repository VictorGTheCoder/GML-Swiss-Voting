"""Extract text from each PDF page, using local OCR only when needed.

OCR is a transcription aid. No result from this module represents semantic
validation of a brochure or its correspondence to an OFS vote.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Callable

import pdfplumber


PageOcr = Callable[[Path, int], str]


def _local_ocr_page(pdf_path: Path, page_number: int) -> str:
    """Rasterize one page with PyMuPDF and run the local Tesseract binary."""
    try:
        import fitz
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "OCR requires the optional Python packages PyMuPDF and pytesseract; "
            "see docs/federal_explanations_pipeline.md"
        ) from exc

    with fitz.open(pdf_path) as document:
        page = document[page_number - 1]
        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        image = Image.open(BytesIO(pixmap.tobytes("png")))
    return pytesseract.image_to_string(image, lang="fra")


def extract_pdf_pages(
    pdf_path: Path,
    *,
    ocr_page: PageOcr | None = None,
) -> list[dict[str, int | str | None]]:
    """Return one stable extraction record per page, retaining page numbers.

    Pages with non-whitespace native text do not invoke OCR. OCR and native
    extraction both retain technical status separately from semantic status.
    A page-level OCR exception is recorded and does not prevent later pages
    from being processed.
    """
    path = Path(pdf_path)
    page_ocr = ocr_page or _local_ocr_page
    records: list[dict[str, int | str | None]] = []

    with pdfplumber.open(path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            native_text = page.extract_text() or ""
            if native_text.strip():
                records.append({
                    "page_number": page_number,
                    "text": native_text,
                    "method": "native",
                    "status": "EXTRACTED",
                    "error": None,
                    "semantic_status": "NOT_VALIDATED",
                })
                continue

            try:
                text = page_ocr(path, page_number) or ""
            except Exception as exc:
                records.append({
                    "page_number": page_number,
                    "text": "",
                    "method": "ocr",
                    "status": "FAILED",
                    "error": str(exc),
                    "semantic_status": "NOT_VALIDATED",
                })
            else:
                records.append({
                    "page_number": page_number,
                    "text": text,
                    "method": "ocr",
                    "status": "EXTRACTED",
                    "error": None,
                    "semantic_status": "NOT_VALIDATED",
                })

    return records
