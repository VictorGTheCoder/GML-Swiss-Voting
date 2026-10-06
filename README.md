# Swiss Voting ML

## Project

Projet GML HEIG-VD portant sur l'analyse et la modélisation des votations fédérales suisses au niveau communal avec des méthodes de Machine Learning.

La problématique exacte et les modèles définitifs sont encore en cours de définition.

## Structure

- `data/` : données brutes, intermédiaires et transformées, non versionnées.
- `scripts/` : pipelines reproductibles de collecte, préparation et audit.
- `notebooks/datasets/` : EDA et exploration par source de données.
- `docs/project/` : décisions et documentation transversales au projet.
- `docs/datasets/<dataset>/README.md` : documentation de référence de chaque source.
- `reports/datasets/` : audits et synthèses humaines versionnés.
- `reports/generated/` : figures et rapports régénérables, non versionnés.

Voir [docs/README.md](docs/README.md) pour l'index de documentation.

## Prérequis

Conda doit être installé au préalable. Vous pouvez installer Miniconda ou Anaconda.

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

Les datasets et artefacts générés ne sont pas versionnés dans Git. Ils doivent être récupérés ou reconstruits via les scripts du projet.

## Development

Le développement se fait par branches, avec des pull requests avant toute intégration importante.
