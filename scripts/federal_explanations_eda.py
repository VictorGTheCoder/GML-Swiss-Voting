"""Generate a small reproducible EDA for the federal explanations corpus.

The script is intentionally downstream-only: it never modifies extraction
outputs. It reads the Parquet files produced by the federal explanations
pipeline and writes a few report-ready PNG figures plus a Markdown summary.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


def _read_optional(path: Path) -> pd.DataFrame | None:
    return pd.read_parquet(path) if path.is_file() else None


def _save(fig: plt.Figure, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def _coverage_status_column(frame: pd.DataFrame) -> str | None:
    for candidate in ("coverage_status", "brochure_status"):
        if candidate in frame.columns:
            return candidate
    return None


def plot_coverage_by_year(coverage: pd.DataFrame, output_dir: Path) -> Path | None:
    if "vote_date" not in coverage.columns or coverage.empty:
        return None

    frame = coverage.copy()
    frame["vote_date"] = pd.to_datetime(frame["vote_date"], errors="coerce")
    frame = frame.dropna(subset=["vote_date"])
    if frame.empty:
        return None

    frame["year"] = frame["vote_date"].dt.year
    status_col = _coverage_status_column(frame)

    fig, ax = plt.subplots(figsize=(11, 5.5))
    if status_col:
        counts = (
            frame.groupby(["year", status_col], dropna=False)
            .size()
            .unstack(fill_value=0)
            .sort_index()
        )
        counts.plot(kind="bar", stacked=True, ax=ax)
        ax.legend(title="Statut")
    else:
        counts = frame.groupby("year").size().sort_index()
        counts.plot(kind="bar", ax=ax)

    ax.set_title("Objets de votation couverts par année")
    ax.set_xlabel("Année")
    ax.set_ylabel("Nombre d'objets")
    ax.tick_params(axis="x", rotation=45)

    path = output_dir / "coverage_by_year.png"
    _save(fig, path)
    return path


def plot_extraction_quality(
    pages: pd.DataFrame | None,
    sections: pd.DataFrame,
    output_dir: Path,
) -> Path | None:
    label = None
    counts = None

    if pages is not None and not pages.empty and "method" in pages.columns:
        counts = pages["method"].fillna("unknown").astype(str).value_counts()
        label = "Méthode d'extraction des pages"
    elif "extraction_status" in sections.columns and not sections.empty:
        counts = sections["extraction_status"].fillna("unknown").astype(str).value_counts()
        label = "Statut d'extraction des sections"

    if counts is None or counts.empty:
        return None

    fig, ax = plt.subplots(figsize=(7, 4.5))
    counts.plot(kind="bar", ax=ax)
    ax.set_title(label)
    ax.set_xlabel("")
    ax.set_ylabel("Nombre")
    ax.tick_params(axis="x", rotation=0)

    path = output_dir / "extraction_quality.png"
    _save(fig, path)
    return path


def _best_text_column(sections: pd.DataFrame) -> str | None:
    for candidate in (
        "full_text",
        "explanatory_text",
        "text",
        "summary_official",
    ):
        if candidate in sections.columns:
            return candidate
    return None


def plot_text_length_distribution(
    sections: pd.DataFrame,
    output_dir: Path,
) -> Path | None:
    text_col = _best_text_column(sections)
    if text_col is None or sections.empty:
        return None

    lengths = sections[text_col].fillna("").astype(str).str.len()
    lengths = lengths[lengths > 0]
    if lengths.empty:
        return None

    bins = max(5, min(30, round(len(lengths) ** 0.5)))
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.hist(lengths, bins=bins)
    ax.set_title("Distribution de la longueur des textes par objet")
    ax.set_xlabel("Nombre de caractères")
    ax.set_ylabel("Nombre d'objets")

    path = output_dir / "text_length_distribution.png"
    _save(fig, path)
    return path


def _model_eligible_count(
    coverage: pd.DataFrame,
    model: pd.DataFrame | None,
) -> int | None:
    if "model_eligible" in coverage.columns:
        values = coverage["model_eligible"]
        if pd.api.types.is_bool_dtype(values):
            return int(values.fillna(False).sum())
        normalized = values.astype(str).str.casefold()
        return int(normalized.isin({"true", "1", "yes"}).sum())

    if "exclusion_reasons" in coverage.columns:
        reasons = coverage["exclusion_reasons"].fillna("").astype(str).str.strip()
        return int((reasons == "").sum())

    if model is not None:
        return len(model)

    return None


def write_report(
    coverage: pd.DataFrame,
    sections: pd.DataFrame,
    pages: pd.DataFrame | None,
    model: pd.DataFrame | None,
    figures: list[Path],
    output_dir: Path,
) -> Path:
    lines = [
        "# EDA — Explications du Conseil fédéral",
        "",
        "Rapport généré automatiquement à partir des exports du pipeline.",
        "",
        "## Couverture",
        "",
        f"- Objets dans le tableau de couverture : **{len(coverage)}**",
        f"- Sections extraites : **{len(sections)}**",
    ]

    if "vote_date" in coverage.columns and not coverage.empty:
        dates = pd.to_datetime(coverage["vote_date"], errors="coerce").dropna()
        if not dates.empty:
            lines.append(
                f"- Période couverte : **{dates.min().date()} → {dates.max().date()}**"
            )

    status_col = _coverage_status_column(coverage)
    if status_col:
        lines.extend(["", "### Statuts de couverture", ""])
        for status, count in coverage[status_col].fillna("unknown").value_counts().items():
            lines.append(f"- `{status}` : **{count}**")

    eligible = _model_eligible_count(coverage, model)
    if eligible is not None:
        lines.extend(["", "## Éligibilité modèle", "", f"- Objets éligibles : **{eligible}**"])

    if pages is not None and not pages.empty:
        lines.extend(["", "## Extraction des pages", "", f"- Pages auditées : **{len(pages)}**"])
        if "method" in pages.columns:
            for method, count in pages["method"].fillna("unknown").value_counts().items():
                lines.append(f"- `{method}` : **{count}**")

    text_col = _best_text_column(sections)
    if text_col:
        lengths = sections[text_col].fillna("").astype(str).str.len()
        nonempty = lengths[lengths > 0]
        if not nonempty.empty:
            lines.extend(
                [
                    "",
                    "## Texte extrait",
                    "",
                    f"- Colonne analysée : `{text_col}`",
                    f"- Objets avec texte non vide : **{len(nonempty)}**",
                    f"- Longueur médiane : **{int(nonempty.median())} caractères**",
                    f"- Longueur moyenne : **{nonempty.mean():.0f} caractères**",
                ]
            )

    lines.extend(["", "## Figures", ""])
    if figures:
        for figure in figures:
            lines.append(f"- [{figure.name}]({figure.name})")
    else:
        lines.append("- Aucune figure générée avec les colonnes disponibles.")

    path = output_dir / "report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def generate_eda(input_dir: Path, output_dir: Path) -> list[Path]:
    coverage_path = input_dir / "coverage.parquet"
    sections_path = input_dir / "sections.parquet"

    if not coverage_path.is_file():
        raise FileNotFoundError(f"Missing required file: {coverage_path}")
    if not sections_path.is_file():
        raise FileNotFoundError(f"Missing required file: {sections_path}")

    coverage = pd.read_parquet(coverage_path)
    sections = pd.read_parquet(sections_path)
    pages = _read_optional(input_dir / "pages.parquet")
    model = _read_optional(input_dir / "model.parquet")

    output_dir.mkdir(parents=True, exist_ok=True)

    figures: list[Path] = []
    for figure in (
        plot_coverage_by_year(coverage, output_dir),
        plot_extraction_quality(pages, sections, output_dir),
        plot_text_length_distribution(sections, output_dir),
    ):
        if figure is not None:
            figures.append(figure)

    report = write_report(coverage, sections, pages, model, figures, output_dir)
    return [*figures, report]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate EDA figures for the federal explanations dataset"
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        required=True,
        help="Directory containing coverage.parquet and sections.parquet",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/federal_explanations_eda"),
        help="Directory where PNG figures and report.md are written",
    )
    args = parser.parse_args()

    generated = generate_eda(args.input_dir, args.output_dir)
    for path in generated:
        print(path)


if __name__ == "__main__":
    main()
