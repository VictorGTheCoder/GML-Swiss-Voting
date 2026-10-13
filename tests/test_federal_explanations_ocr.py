import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.federal_explanations.federal_explanations_ocr import extract_pdf_pages


def _pdf_with_text(path: Path, text: str) -> None:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = ("BT /F1 12 Tf 50 750 Td (" + escaped + ") Tj ET").encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    path.write_bytes(pdf)


def test_extract_pages_uses_native_text_and_ocr_only_for_scanned_pages(tmp_path):
    pdf = tmp_path / "mixed.pdf"
    _pdf_with_text(pdf, "Native page")
    calls = []

    def ocr_page(path, page_number):
        calls.append((path, page_number))
        return "OCR page"

    pages = extract_pdf_pages(pdf, ocr_page=ocr_page)

    assert [page["page_number"] for page in pages] == [1]
    assert pages[0]["text"] == "Native page"
    assert pages[0]["method"] == "native"
    assert pages[0]["status"] == "EXTRACTED"
    assert pages[0]["semantic_status"] == "NOT_VALIDATED"
    assert calls == []


def test_page_records_preserve_page_reference_and_ocr_failure(tmp_path):
    pdf = tmp_path / "scan.pdf"
    _pdf_with_text(pdf, "   ")

    def failed_ocr(path, page_number):
        raise RuntimeError("tesseract unavailable")

    pages = extract_pdf_pages(pdf, ocr_page=failed_ocr)

    assert pages == [{
        "page_number": 1,
        "text": "",
        "method": "ocr",
        "status": "FAILED",
        "error": "tesseract unavailable",
        "semantic_status": "NOT_VALIDATED",
    }]


def test_ocr_success_is_extracted_but_still_requires_semantic_review(tmp_path):
    pdf = tmp_path / "scan.pdf"
    _pdf_with_text(pdf, "")

    pages = extract_pdf_pages(pdf, ocr_page=lambda path, page_number: "Objet 1: Texte reconnu")

    assert pages[0]["text"] == "Objet 1: Texte reconnu"
    assert pages[0]["method"] == "ocr"
    assert pages[0]["status"] == "EXTRACTED"
    assert pages[0]["semantic_status"] == "NOT_VALIDATED"


def test_extraction_preserves_original_pdf_bytes(tmp_path):
    pdf = tmp_path / "source.pdf"
    _pdf_with_text(pdf, "Source")
    original = pdf.read_bytes()

    extract_pdf_pages(pdf, ocr_page=lambda path, page_number: "OCR")

    assert pdf.read_bytes() == original
