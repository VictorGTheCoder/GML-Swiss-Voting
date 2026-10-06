import json
import subprocess
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "scripts" / "federal_explanations.py"


def _pdf_with_text(path: Path, text: str) -> None:
    """Write a tiny one-page PDF text fixture without external services."""
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    lines = escaped.split("\n")
    commands = [f"({line}) Tj 0 -20 Td" for line in lines]
    stream = ("BT /F1 12 Tf 50 750 Td " + " ".join(commands) + " ET").encode("latin-1")
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
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode())
    path.write_bytes(pdf)


def _run_pipeline(tmp_path: Path, *, confirmed: bool = True, ambiguous: bool = False):
    pdf = tmp_path / "brochure.pdf"
    _pdf_with_text(
        pdf,
        "Objet 1: Initiative pour des soins accessibles\n"
        "Resume officiel: Le projet garantit un acces equitable aux soins.\n"
        "Texte complet: L'initiative demande que la Confederation agisse.\n"
        "Conseil federal: rejeter l'initiative\n"
        "Parlement: accepter l'initiative",
    )
    votes = tmp_path / "ofs.csv"
    pd.DataFrame(
        [{"vote_id": "6021", "vote_date": "2024-06-09", "question_fr": "Initiative pour des soins accessibles",
          "is_tiebreak_question": False}]
    ).to_csv(votes, index=False)
    manifest = tmp_path / "sources.json"
    manifest.write_text(json.dumps({"documents": [{
        "source_id": "bk-2024-06-09-fr", "pdf_path": str(pdf),
        "official_url": "https://www.bk.admin.ch/fr/example.pdf", "vote_date": "2024-06-09",
        "language": "fr", "collected_at": "2026-10-06T10:00:00Z",
        "availability_status": "CONFIRMED_PRE_VOTE" if confirmed else "INVESTIGATE",
        "availability_evidence": "Brochure archived before voting day" if confirmed else "No pre-vote publication proof",
        "ofs_vote_id": "6021", "match_status": "PROPOSED" if ambiguous else "VALIDATED",
        "match_justification": "Official question title matches the section title",
    }]}), encoding="utf-8")
    out = tmp_path / "out"
    result = subprocess.run(
        [sys.executable, str(ENTRYPOINT), "--ofs", str(votes), "--sources", str(manifest), "--output", str(out)],
        capture_output=True, text=True,
    )
    return result, out, pdf


def test_pipeline_exports_one_official_section_and_model_row(tmp_path):
    result, output, pdf = _run_pipeline(tmp_path)
    assert result.returncode == 0, result.stderr

    coverage = pd.read_parquet(output / "coverage.parquet")
    sections = pd.read_parquet(output / "sections.parquet")
    links = pd.read_parquet(output / "section_links.parquet")
    model = pd.read_parquet(output / "model.parquet")
    assert coverage.loc[0, "vote_id"] == "6021"
    assert sections.loc[0, "title"] == "Initiative pour des soins accessibles"
    assert sections.loc[0, "summary_official"].startswith("Le projet garantit")
    assert sections.loc[0, "full_text"].startswith("L") and "demande" in sections.loc[0, "full_text"]
    assert sections.loc[0, "council_recommendation_raw"].startswith("rejeter")
    assert sections.loc[0, "parliament_recommendation_raw"].startswith("accepter")
    assert sections.loc[0, "source_pages"] == "1"
    assert sections.loc[0, "pdf_sha256"]
    assert links.loc[0, "ofs_vote_id"] == "6021"
    assert len(model) == 1
    assert (output / "report.md").exists()
    assert list((output / "originals").glob("*.pdf"))
    assert pdf.read_bytes()


def test_pipeline_excludes_unproven_or_ambiguous_object(tmp_path):
    for label, options in [("unproven", {"confirmed": False}), ("ambiguous", {"ambiguous": True})]:
        case = tmp_path / label
        case.mkdir()
        result, output, _ = _run_pipeline(case, **options)
        assert result.returncode == 0, result.stderr
        model = pd.read_parquet(output / "model.parquet")
        report = (output / "report.md").read_text(encoding="utf-8")
        assert model.empty
        assert label in report.lower() or ("pre-vote" if label == "unproven" else "ambiguous") in report.lower()


def test_pipeline_is_offline_idempotent_and_preserves_pdf_versions(tmp_path):
    result, output, pdf = _run_pipeline(tmp_path)
    assert result.returncode == 0, result.stderr
    before = {path.name: path.read_bytes() for path in output.iterdir() if path.is_file()}
    original_hash = __import__("hashlib").sha256(pdf.read_bytes()).hexdigest()
    # The entry point must use the supplied local files and must not need network access.
    second = subprocess.run(
        [sys.executable, str(ENTRYPOINT), "--ofs", str(tmp_path / "ofs.csv"), "--sources", str(tmp_path / "sources.json"), "--output", str(output)],
        capture_output=True, text=True,
    )
    assert second.returncode == 0, second.stderr
    assert before == {path.name: path.read_bytes() for path in output.iterdir() if path.is_file()}
    assert __import__("hashlib").sha256(pdf.read_bytes()).hexdigest() == original_hash
    assert len(list((output / "originals").glob("*.pdf"))) == 1
