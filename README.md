# Swiss Voting ML

## Project

Projet GML HEIG-VD portant sur l'analyse et la modélisation des votations fédérales suisses au niveau communal avec des méthodes de Machine Learning.

La problématique exacte et les modèles définitifs sont encore en cours de définition.

## Structure

- `data/` : datasets non versionnés — `raw/` (tel que fourni par la source, jamais modifié), `interim/`, `processed/`.
- `scripts/` : scripts Python exécutables pour récupérer et préparer les données.
- `notebooks/` : notebooks d'exploration, EDA et essais (le pipeline n'en dépend pas).
- `reports/` : rapports d'audit et de validation générés par les scripts.
- `docs/` : cahier des charges, notes méthodologiques et documentation du projet.
- `tests/` : tests unitaires (`python -m pytest`).

## Prérequis

Conda doit être installé au préalable. Vous pouvez installer
[Miniconda](https://docs.conda.io/projects/miniconda/en/latest/) ou Anaconda.

Vérifiez l'installation avec :

```bash
conda --version
```

## Setup

L'environnement Conda du projet est défini dans `environment.yml`.

Première installation :

```bash
conda env create -f environment.yml
conda activate swiss-votes-ml
```

Mise à jour de l'environnement :

```bash
conda env update -f environment.yml --prune
conda activate swiss-votes-ml
```

L'option `--prune` supprime également les paquets qui ne figurent plus dans `environment.yml`.

## Data

Les datasets ne sont pas versionnés dans Git ; ils se reconstruisent depuis les sources officielles.

Résultats communaux des votations fédérales (OFS `px-x-1703030000_101`) → `data/processed/votes_communes.parquet`
(une ligne par commune × objet, avec `yes_share`) :

```bash
python scripts/build_dataset.py   # téléchargement si nécessaire, audit, nettoyage, validation
```

Provenance, schéma, particularités (fusions de communes, unités spéciales, questions subsidiaires) :
[`docs/DATA_VOTES.md`](docs/DATA_VOTES.md). Audit chiffré : [`reports/data_audit.md`](reports/data_audit.md).

## Development

Le développement se fait par branches, avec des pull requests avant toute intégration importante.
