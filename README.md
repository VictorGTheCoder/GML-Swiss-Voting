# Swiss Voting ML

## Project

Projet GML HEIG-VD portant sur l'analyse et la modélisation des votations fédérales suisses au niveau communal avec des méthodes de Machine Learning.

La problématique exacte et les modèles définitifs sont encore en cours de définition.

## Structure

- `data/` : datasets bruts ou transformés, non versionnés.
- `scripts/` : scripts Python exécutables pour récupérer et préparer les données.
- `notebooks/` : notebooks d'exploration, EDA et essais.
- `docs/` : cahier des charges, notes méthodologiques et documentation du projet.

## Setup

```bash
python -m venv .venv
```

Linux/macOS :

```bash
source .venv/bin/activate
```

Windows :

```powershell
.venv\Scripts\activate
```

Installer les dépendances :

```bash
pip install -r requirements.txt
```

## Data

Les datasets ne sont pas versionnés dans Git. Ils devront être récupérés ou reconstruits via les scripts du projet.

## Development

Le développement se fait par branches, avec des pull requests avant toute intégration importante.
