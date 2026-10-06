"""Generate reproducible EDA figures for the Federal Council explanations corpus."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


def _save(fig: plt.Figure, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def plot_coverage_by_year(objects: pd.DataFrame, output_dir: Path) -> Path | None:
    if objects.empty or "vote_date" not in objects.columns:
        return None

    frame = objects.copy()
    frame["vote_date"] = pd.to_datetime(frame["vote_date"], errors="coerce")
    frame = frame.dropna(subset=["vote_date"])
    if frame.empty:
        return None

    frame["year"] = frame["vote_date"].dt.year
    fig, ax = plt.subplots(figsize=(11, 5.5))

    if "brochure_status" in frame.columns:
        counts = (
            frame.groupby(["year", "brochure_status"], dropna=False)
            .size()
            .unstack(fill_value=0)
            .sort_index()
        )
        counts.plot(kind="bar", stacked=True, ax=ax)
        ax.legend(title="Statut")
    else:
        frame.groupby("year").size().sort_index().plot(kind="bar", ax=ax)

    ax.set_title("Objets de votation couverts par année")
    ax.set_xlabel("Année")
    ax.set_ylabel("Nombre d'objets")
    ax.tick_params(axis="x", rotation=45)

    path = output_dir / "coverage_by_year.png"
    _save(fig, path)
    return path


def plot_extraction_quality(pages: pd.DataFrame, output_dir: Path) -> Path | None:
    if pages.empty or "method" not in pages.columns:
        return None

    counts = pages["method"].fillna("unknown").astype(str).value_counts()

    fig, ax = plt.subplots(figsize=(7, 4.5))
    counts.plot(kind="bar", ax=ax)
    ax.set_title("Méthode d'extraction des pages")
    ax.set_xlabel("")
    ax.set_ylabel("Nombre")
    ax.tick_params(axis="x", rotation=0)

    path = output_dir / "extraction_quality.png"
    _save(fig, path)
    return path


def plot_text_length_distribution(
    sections: pd.DataFrame,
    output_dir: Path,
) -> Path | None:
    if sections.empty or "full_text" not in sections.columns:
        return None

    lengths = sections["full_text"].fillna("").astype(str).str.len()
    lengths = lengths[lengths > 0]
    if lengths.empty:
        return None

    bins = max(5, min(30, round(len(lengths) ** 0.5)))
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.hist(lengths, bins=bins)
    ax.set_title("Distribution de la longueur des textes par section")
    ax.set_xlabel("Nombre de caractères")
    ax.set_ylabel("Nombre de sections")

    path = output_dir / "text_length_distribution.png"
    _save(fig, path)
    return path


def write_report(
    objects: pd.DataFrame,
    sections: pd.DataFrame,
    pages: pd.DataFrame,
    figures: list[Path],
    output_dir: Path,
) -> Path:
    lines = [
        "# EDA — Explications du Conseil fédéral",
        "",
        f"- Objets OFS raccordés au corpus : **{len(objects)}**",
        f"- Sections extraites : **{len(sections)}**",
        f"- Pages extraites : **{len(pages)}**",
    ]

    if "vote_date" in objects.columns:
        dates = pd.to_datetime(objects["vote_date"], errors="coerce").dropna()
        if not dates.empty:
            lines.append(
                f"- Période couverte : **{dates.min().date()} → {dates.max().date()}**"
            )

    if "brochure_status" in objects.columns:
        found = int((objects["brochure_status"] == "FOUND").sum())
        lines.append(f"- Objets avec brochure trouvée : **{found}/{len(objects)}**")

    if "method" in pages.columns:
        lines.extend(["", "## Extraction des pages", ""])
        for method, count in pages["method"].fillna("unknown").value_counts().items():
            lines.append(f"- {method} : **{count}**")

    if "full_text" in sections.columns:
        lengths = sections["full_text"].fillna("").astype(str).str.len()
        nonempty = lengths[lengths > 0]
        if not nonempty.empty:
            lines.extend(
                [
                    "",
                    "## Texte extrait",
                    "",
                    f"- Sections avec texte non vide : **{len(nonempty)}**",
                    f"- Longueur médiane : **{int(nonempty.median())} caractères**",
                    f"- Longueur moyenne : **{nonempty.mean():.0f} caractères**",
                ]
            )

    lines.extend(["", "## Figures", ""])
    for figure in figures:
        lines.append(f"- [{figure.name}]({figure.name})")

    path = output_dir / "report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def generate_eda(input_dir: Path, output_dir: Path) -> list[Path]:
    objects = pd.read_parquet(input_dir / "objects.parquet")
    sections = pd.read_parquet(input_dir / "sections.parquet")
    pages = pd.read_parquet(input_dir / "pages.parquet")

    output_dir.mkdir(parents=True, exist_ok=True)

    figures = [
        figure
        for figure in (
            plot_coverage_by_year(objects, output_dir),
            plot_extraction_quality(pages, output_dir),
            plot_text_length_distribution(sections, output_dir),
        )
        if figure is not None
    ]

    report = write_report(objects, sections, pages, figures, output_dir)
    return [*figures, report]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate EDA figures for the federal explanations dataset"
    )
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/generated/federal_explanations/eda"),
    )
    args = parser.parse_args()

    for path in generate_eda(args.input_dir, args.output_dir):
        print(path)


if __name__ == "__main__":
    main()
