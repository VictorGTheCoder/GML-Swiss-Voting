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


def _vote_index(
    sources: pd.DataFrame,
    section_links: pd.DataFrame,
) -> pd.DataFrame:
    """Build a minimal vote/date index from Chancellery sources and link candidates."""
    if section_links.empty:
        return pd.DataFrame(columns=["vote_id", "vote_date"])

    links = section_links[["vote_id", "source_id"]].drop_duplicates()
    source_dates = sources[["source_id", "vote_date"]].drop_duplicates()
    votes = links.merge(source_dates, on="source_id", how="left")
    return votes[["vote_id", "vote_date"]].drop_duplicates()


def plot_coverage_by_year(
    sources: pd.DataFrame,
    section_links: pd.DataFrame,
    output_dir: Path,
) -> Path | None:
    votes = _vote_index(sources, section_links)
    if votes.empty:
        return None

    votes["vote_date"] = pd.to_datetime(votes["vote_date"], errors="coerce")
    votes = votes.dropna(subset=["vote_date"])
    if votes.empty:
        return None

    votes["year"] = votes["vote_date"].dt.year
    counts = votes.groupby("year")["vote_id"].nunique().sort_index()

    fig, ax = plt.subplots(figsize=(11, 5.5))
    counts.plot(kind="bar", ax=ax)
    ax.set_title("Objets de votation reliés au corpus par année")
    ax.set_xlabel("Année")
    ax.set_ylabel("Nombre d'objets OFS")
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
    ax.set_ylabel("Nombre de pages")
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
    sources: pd.DataFrame,
    sections: pd.DataFrame,
    pages: pd.DataFrame,
    section_links: pd.DataFrame,
    figures: list[Path],
    output_dir: Path,
) -> Path:
    votes = _vote_index(sources, section_links)
    lines = [
        "# EDA — Explications du Conseil fédéral",
        "",
        f"- Brochures : **{len(sources)}**",
        f"- Objets OFS reliés au corpus : **{votes['vote_id'].nunique()}**",
        f"- Sections extraites : **{len(sections)}**",
        f"- Pages extraites : **{len(pages)}**",
    ]

    dates = pd.to_datetime(sources["vote_date"], errors="coerce").dropna()
    if not dates.empty:
        lines.append(
            f"- Période couverte : **{dates.min().date()} → {dates.max().date()}**"
        )

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
    sources = pd.read_parquet(input_dir / "sources.parquet")
    sections = pd.read_parquet(input_dir / "sections.parquet")
    pages = pd.read_parquet(input_dir / "pages.parquet")
    section_links = pd.read_parquet(input_dir / "section_links.parquet")

    output_dir.mkdir(parents=True, exist_ok=True)

    figures = [
        figure
        for figure in (
            plot_coverage_by_year(sources, section_links, output_dir),
            plot_extraction_quality(pages, output_dir),
            plot_text_length_distribution(sections, output_dir),
        )
        if figure is not None
    ]

    report = write_report(
        sources,
        sections,
        pages,
        section_links,
        figures,
        output_dir,
    )
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
