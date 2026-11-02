"""Generate exploratory figures for the first project presentation.

Usage: python -m scripts.integration.presentation_figures
Reads the exploratory commune x object table and writes PNG files under
reports/generated/presentation/. Retrospective analysis only, not forecast evidence.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import patheffects

from scripts.boundaries.download_boundaries import EXTRACTED_DIR

ROOT = Path(__file__).resolve().parents[2]
MODELING = ROOT / "data" / "processed" / "modeling" / "municipal_structured.parquet"
CROSSWALK = ROOT / "data" / "processed" / "repertoire_communes" / "crosswalk_2010-01-01_to_2026-01-01.csv"
VOTES = ROOT / "data" / "processed" / "ofs-votes" / "votes_communes.parquet"
OUT = ROOT / "reports" / "presentation"
RECENT_FROM = pd.Timestamp("2023-01-01")  # objects shown on the example maps

INK, MUTED, GRID = "#1f2937", "#6b7280", "#e5e7eb"
BLUE, RED, GRAY = "#163f73", "#c62828", "#9ca3af"
SEQ = plt.cm.Blues

DOMAINS = {
    1: "Ordre politique", 2: "Politique extérieure", 3: "Sécurité", 4: "Économie",
    5: "Agriculture", 6: "Finances publiques", 7: "Énergie", 8: "Transports",
    9: "Environnement", 10: "Politique sociale", 11: "Formation, recherche", 12: "Culture, médias",
}
LEGAL = {1: "Référendum obligatoire", 2: "Référendum facultatif", 3: "Initiative populaire", 4: "Contre-projet"}
LANG = {1: "Allemand", 2: "Français", 3: "Italien", 4: "Romanche"}
URBAN = {1: "Urbain", 2: "Intermédiaire", 3: "Rural"}
PARTIES = {
    "party_share_udc": "UDC", "party_share_ps": "PS", "party_share_plr": "PLR", "party_share_verts": "Verts",
    "party_share_pvl": "PVL", "party_share_pdc": "PDC", "party_share_pev": "PEV",
}

def style() -> None:
    plt.rcParams.update({
        "figure.dpi": 130, "savefig.dpi": 200, "font.size": 11, "axes.edgecolor": GRID,
        "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK,
        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
        "axes.axisbelow": True, "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlelocation": "left",
    })


def save(fig: plt.Figure, name: str) -> None:
    fig.tight_layout()
    fig.savefig(OUT / f"{name}.png", facecolor="white")
    plt.close(fig)


def load() -> pd.DataFrame:
    d = pd.read_parquet(MODELING)
    for col in ["yes_share", "history_mean_yes", *PARTIES]:
        d[col] = d[col].astype(float)
    d["object_mean"] = d.groupby("vote_id")["yes_share"].transform("mean")
    d["dev"] = d["yes_share"] - d["object_mean"]
    d["year"] = d["vote_date"].dt.year
    return d


def fig_overview(d: pd.DataFrame) -> None:
    per_year = d.groupby("year").agg(objets=("vote_id", "nunique"), communes=("municipality_id", "nunique"))
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.bar(per_year.index, per_year["objets"], color=BLUE, width=0.7)
    ax.set_title("Nombre d'objets fédéraux par année")
    ax.set_ylabel("Objets")
    ax.grid(axis="x", visible=False)
    ax.text(0.99, 0.95, f"{len(d):,} lignes · {d.municipality_id.nunique():,} communes · {d.vote_id.nunique()} objets"
            .replace(",", " "), transform=ax.transAxes, ha="right", va="top", color=MUTED)
    save(fig, "01_apercu_objets_par_annee")


def fig_target_distribution(d: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4), gridspec_kw={"width_ratios": [1, 1.2]})
    axes[0].hist(d["yes_share"] * 100, bins=60, color=BLUE, edgecolor="white", linewidth=0.3)
    axes[0].axvline(50, color=MUTED, ls="--", lw=1)
    axes[0].set_title("Part de « oui » (commune × objet)")
    axes[0].set_xlabel("Part de oui (%)")
    axes[0].set_ylabel("Observations")
    forms = [k for k in LEGAL if k in set(d.object_legal_form.astype(int))]
    data = [d.loc[d.object_legal_form.astype(int) == k, "yes_share"] * 100 for k in forms]
    bp = axes[1].boxplot(data, vert=False, patch_artist=True, showfliers=False, widths=0.55,
                         medianprops={"color": INK, "lw": 1.8})
    for box in bp["boxes"]:
        box.set(facecolor=BLUE, alpha=0.55, edgecolor=BLUE)
    axes[1].set_yticklabels([f"{LEGAL[k]}\n(n={len(x):,})".replace(",", " ") for k, x in zip(forms, data, strict=True)])
    axes[1].axvline(50, color=MUTED, ls="--", lw=1)
    axes[1].set_title("Selon la forme juridique de l'objet")
    axes[1].set_xlabel("Part de oui (%)")
    save(fig, "02_distribution_cible")


def fig_groups(d: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    for ax, (col, labels, title) in zip(axes, [("language_region", LANG, "Région linguistique"),
                                               ("urban_rural", URBAN, "Type de commune")], strict=True):
        g = d.groupby(col)["dev"].mean().mul(100)
        n = d.groupby(col)["municipality_id"].nunique()
        names = [f"{labels[int(k)]}\n({n[k]:,} communes)".replace(",", " ") for k in g.index]
        colors = [BLUE if v >= 0 else RED for v in g]
        ax.bar(names, g.values, color=colors, width=0.6)
        for i, v in enumerate(g.values):
            ax.text(i, v + (0.4 if v >= 0 else -0.4), f"{v:+.1f}", ha="center", va="bottom" if v >= 0 else "top")
        ax.axhline(0, color=MUTED, lw=1)
        ax.set_title(title)
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("Écart à la moyenne de l'objet (points)")
    save(fig, "04_langue_urbain_rural")


def fig_correlations(d: pd.DataFrame) -> None:
    feats = {**PARTIES, "statpop_share_foreign": "Part d'étrangers", "statpop_mean_age": "Âge moyen",
             "statpop_share_65_plus": "Part des 65+", "statpop_share_20_39": "Part des 20-39",
             "statpop_pop_total": "Population (log)"}
    rows = {}
    for col, label in feats.items():
        x = d[col].astype(float)
        if col == "statpop_pop_total":
            x = np.log10(x)
        rows[label] = x.corr(d["dev"])
    s = pd.Series(rows).sort_values()
    fig, ax = plt.subplots(figsize=(8.5, 5))
    ax.barh(s.index, s.values, color=[BLUE if v >= 0 else RED for v in s.values], height=0.65)
    for i, v in enumerate(s.values):
        ax.text(v + (0.01 if v >= 0 else -0.01), i, f"{v:+.2f}", va="center", ha="left" if v >= 0 else "right")
    ax.axvline(0, color=MUTED, lw=1)
    ax.set_xlim(s.min() - 0.1, s.max() + 0.1)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Corrélation avec l'écart à la moyenne de l'objet")
    ax.set_title("Quelles caractéristiques communales vont avec plus de « oui » ?")
    save(fig, "05_correlations_variables")


def fig_theme_effect(d: pd.DataFrame) -> None:
    rows = []
    for dom, g in d.groupby(d.object_domain_1.astype(int)):
        rows.append({"domaine": DOMAINS[dom], "UDC": g["party_share_udc"].corr(g["dev"]),
                     "PS": g["party_share_ps"].corr(g["dev"])})
    t = pd.DataFrame(rows).set_index("domaine").sort_values("UDC")
    y = np.arange(len(t))
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(y - 0.19, t["UDC"], height=0.36, color=BLUE, label="Part UDC")
    ax.barh(y + 0.19, t["PS"], height=0.36, color=RED, label="Part PS")
    ax.set_yticks(y, t.index)
    ax.axvline(0, color=MUTED, lw=1)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Corrélation avec l'écart à la moyenne de l'objet")
    ax.set_title("Le lien parti ↔ « oui » dépend du thème de l'objet")
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2)
    save(fig, "06_effet_parti_par_theme")


def fig_domains(d: pd.DataFrame) -> None:
    objs = d.drop_duplicates("vote_id")
    c = objs["object_domain_1"].astype(int).map(DOMAINS).value_counts().sort_values()
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(c.index, c.values, color=BLUE, height=0.65)
    for i, v in enumerate(c.values):
        ax.text(v + 0.2, i, str(v), va="center")
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Nombre d'objets")
    ax.set_title("Thème principal des objets (Swissvotes, domaine 1)")
    save(fig, "07_themes_des_objets")


def fig_mergers() -> None:
    c = pd.read_csv(CROSSWALK)
    rel = c.groupby("relation")["source_code"].nunique().sort_values()
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.barh(rel.index, rel.values, color=BLUE, height=0.6)
    for i, v in enumerate(rel.values):
        ax.text(v + 15, i, f"{v:,}".replace(",", " "), va="center")
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Communes de 2010")
    ax.set_title("Fusions de communes entre 2010 et 2026 (crosswalk)")
    save(fig, "08_fusions_communes")


def load_geometries():
    """Commune and canton polygons (swissBOUNDARIES3D 2026-01), 2D and simplified for plotting."""
    import geopandas as gpd

    def read(name: str):
        g = gpd.read_file(EXTRACTED_DIR / f"swissBOUNDARIES3D_1_5_TLM_{name}.shp")
        g["geometry"] = gpd.GeoSeries(g.geometry).force_2d().simplify(150)
        return g

    communes = read("HOHEITSGEBIET")
    communes = communes[(communes["OBJEKTART"] == "Gemeindegebiet") & (communes["ICC"] == "CH")].copy()
    communes["municipality_id"] = communes["BFS_NUMMER"].astype(int).astype(str).str.zfill(4)
    return communes, read("KANTONSGEBIET")


def draw_map(communes, cantons, values: pd.Series, title: str, cbar_label: str, name: str, *, diverging: bool,
             lim: float | None = None, center: float = 0.0, labels=()) -> None:
    g = communes.merge(values.rename("value"), left_on="municipality_id", right_index=True, how="left")
    fig, ax = plt.subplots(figsize=(11, 7))
    if diverging:
        lim = lim or float(np.nanpercentile(np.abs(g["value"] - center), 98))
        norm, cmap = plt.Normalize(center - lim, center + lim), plt.cm.RdBu_r
    else:
        norm, cmap = plt.Normalize(float(np.nanpercentile(g["value"], 2)), float(np.nanpercentile(g["value"], 98))), SEQ
    g.plot(column="value", cmap=cmap, norm=norm, ax=ax, linewidth=0, missing_kwds={"color": GRID})
    cantons.boundary.plot(ax=ax, color="white", linewidth=0.5)
    for x, y, txt in labels:
        ax.text(x, y, txt, ha="center", va="center", fontsize=8, fontweight="bold", color=INK,
                path_effects=[patheffects.withStroke(linewidth=2.5, foreground="white")])
    ax.axis("off")
    ax.set_title(title)
    fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), ax=ax, shrink=0.55, label=cbar_label)
    save(fig, name)


def maps(d: pd.DataFrame) -> None:
    communes, cantons = load_geometries()
    mean_dev = d.groupby("municipality_id")["dev"].mean() * 100
    draw_map(communes, cantons, mean_dev, "Profil de vote des communes : écart moyen à la moyenne de l'objet",
             "Écart moyen (points de %)", "09_carte_communes_profil", diverging=True)

    recent = d[d["vote_date"] >= RECENT_FROM]
    canton_of = d.drop_duplicates("municipality_id").set_index("municipality_id")["canton"]
    canton_dev = d.groupby("canton")["dev"].mean() * 100
    communes["canton"] = communes["municipality_id"].map(canton_of)
    labels = []
    for c, geom in communes.dissolve("canton").geometry.items():
        main_part = max(geom.geoms, key=lambda g: g.area) if geom.geom_type == "MultiPolygon" else geom
        p = main_part.centroid if main_part.contains(main_part.centroid) else main_part.representative_point()
        if c in canton_dev:
            labels.append((p.x, p.y, f"{c}\n{canton_dev[c]:+.1f}"))
    draw_map(communes, cantons, communes.set_index("municipality_id")["canton"].map(canton_dev),
             "Écart moyen à la moyenne de l'objet, par canton (points)", "Écart moyen (points de %)",
             "03_carte_cantons_ecart", diverging=True, labels=labels)

    spread = recent.groupby("vote_id")["yes_share"].std().sort_values(ascending=False)
    titles = pd.read_parquet(VOTES, columns=["vote_id", "vote_title_fr", "vote_date"]).drop_duplicates("vote_id")
    titles = titles.set_index("vote_id")
    for rank, vote_id in enumerate(spread.index[:3], start=1):
        sub = d[d["vote_id"] == vote_id].set_index("municipality_id")["yes_share"] * 100
        t = titles.loc[vote_id]
        title = f"{t.vote_date:%d.%m.%Y}\n" + textwrap.fill(t.vote_title_fr, width=75)
        draw_map(communes, cantons, sub, title, "Part de oui (%)", f"{9 + rank}_carte_objet_{rank}", diverging=True, lim=50, center=50)
    for col, label, name in [("party_share_udc", "Part UDC (%)", "13_carte_udc"),
                             ("statpop_share_foreign", "Part d'étrangers (%)", "14_carte_etrangers")]:
        last = d.sort_values("vote_date").drop_duplicates("municipality_id", keep="last").set_index("municipality_id")
        v = last[col].astype(float) * (100 if col.startswith("party") else 1)
        draw_map(communes, cantons, v, label + " par commune", label, name, diverging=False)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    style()
    d = load()
    for fn in (fig_overview, fig_target_distribution, fig_groups, fig_correlations, fig_theme_effect, fig_domains):
        fn(d)
    fig_mergers()
    maps(d)
    print(f"Figures written to {OUT}")


if __name__ == "__main__":
    main()
