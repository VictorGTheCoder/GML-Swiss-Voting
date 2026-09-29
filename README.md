# Swiss Voting ML

## Project

Projet GML HEIG-VD portant sur l'analyse et la modélisation des votations fédérales suisses au niveau communal avec des méthodes de Machine Learning.

La problématique exacte et les modèles définitifs sont encore en cours de définition.

## Structure

- `data/` : datasets bruts ou transformés, non versionnés.
- `scripts/` : scripts Python exécutables pour récupérer et préparer les données.
- `notebooks/` : notebooks d'exploration, EDA et essais.
- `docs/` : cahier des charges, notes méthodologiques et documentation du projet.

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

Les datasets ne sont pas versionnés dans Git. Ils devront être récupérés ou reconstruits via les scripts du projet.

## Development

Le développement se fait par branches, avec des pull requests avant toute intégration importante.
