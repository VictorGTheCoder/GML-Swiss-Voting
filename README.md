# Swiss Voting ML — projet GML

## Sujet en cours de cadrage

Projet HEIG-VD : prédire la part de « oui » d'un objet de votation **cantonale** suisse à partir de son titre et de caractéristiques institutionnelles disponibles avant le scrutin, puis évaluer cette prédiction sur des dates ultérieures.

Le [plan de travail cantonal](docs/plan-votations-cantonales.md) détaille les étapes, critères de sortie, exigences du cours et points méthodologiques. Le cahier des charges doit encore être actualisé et validé par l'équipe et les enseignants.

**État du dépôt :** les scripts actuels `scripts/download_votes.py`, `scripts/build_dataset.py` et associés traitent l'**ancien sujet fédéral/communal** fondé sur l'OFS. L'audit `docs/communal_features_audit.md` conserve la trace de ce travail. Ces scripts ne produisent pas le dataset C2D cantonal annoncé dans le nouveau plan.

## Structure

- `data/` : données brutes et transformées, non versionnées.
- `scripts/` : scripts de l'ancien pipeline OFS, à classer lors du pivot.
- `notebooks/` : exploration et essais.
- `docs/` : plan, audits et documentation.

## Prérequis et environnement

Conda doit être installé. L'environnement est défini dans `environment.yml`.

```bash
conda env create -f environment.yml
conda activate swiss-votes-ml
```

Mise à jour :

```bash
conda env update -f environment.yml --prune
conda activate swiss-votes-ml
```

Les données ne sont pas versionnées dans Git. La procédure reproductible de collecte C2D reste à réaliser. Le développement se fait par branches et pull requests.
