# Swiss Voting ML

Projet GML de la HEIG-VD consacré à l'analyse et à la prédiction des **résultats des votations fédérales suisses au niveau communal** à l'aide du machine learning.

## Objectif

**Question principale :** dans quelle mesure les résultats électoraux passés et les caractéristiques des communes et des objets soumis au vote permettent-ils d'estimer la part de « oui » d'une commune pour un nouvel objet fédéral ?

- **Unité d'observation :** commune × objet de votation fédérale.
- **Cible :** proportion de « oui » parmi les suffrages valables, soit `oui / (oui + non)`.
- **Approche :** construire un dataset reproductible, comparer des références historiques à des modèles supervisés, analyser leurs erreurs et restituer les résultats dans une application utilisable.
- **Limite d'interprétation :** les résultats communaux sont agrégés et ne permettent pas d'inférer le vote individuel ni de démontrer des causalités.

Le projet porte sur les **votations fédérales**, avec des prédictions **par commune** ; ce n'est pas un modèle de prédiction des votations cantonales à partir de C2D.

## Données retenues

Le périmètre des sources **Must** est défini dans [docs/project/datasets.md](docs/project/datasets.md). L'inclusion effective d'une variable dans un modèle dépendra de sa disponibilité, de la qualité de sa jointure et de son admissibilité temporelle.

| Source | Rôle |
| --- | --- |
| **OFS — résultats des votations fédérales par commune** | Cible, participation et historique électoral communal (source centrale, historique depuis 1960) |
| **OFS — STATPOP** | Population et structure démographique |
| **OFS — force des partis par commune** | Profil électoral à partir des élections précédentes |
| **OFS — typologies territoriales et régions linguistiques** | Contexte géographique et linguistique |
| **Swissvotes** | Métadonnées et thèmes des objets soumis au vote |
| **Chancellerie fédérale — explications du Conseil fédéral** | Titres, textes et recommandations issus des brochures officielles |

Le **répertoire historique des communes de l'OFS** sert à harmoniser les identifiants et les mutations territoriales entre les sources ; ce n'est pas une variable prédictive en soi.

### Règle de validation temporelle

Une variable utilisée pour prédire un scrutin doit avoir été **disponible avant sa date**. Cela implique notamment :

- une évaluation chronologique, en regroupant les observations d'une même date de votation ;
- des historiques de vote calculés uniquement à partir de scrutins antérieurs ;
- des données démographiques, électorales et territoriales jointes selon une version et une date de publication admissibles ;
- des traitements ajustés sur l'entraînement seulement et aucune utilisation des résultats du scrutin prédit dans ses entrées.

Les partitions, les références historiques et les métriques définitives sont à documenter dans le protocole d'évaluation, sans reprendre automatiquement celles d'une ancienne étude cantonale.

## Structure du dépôt

- `data/` : sources brutes, données intermédiaires et données préparées ; les données brutes et caches restent hors Git.
- `scripts/` : pipelines reproductibles de collecte, préparation, contrôle et audit.
- `notebooks/datasets/` : exploration (EDA) par source.
- `docs/project/` : périmètre, décisions et audits transversaux.
- `docs/datasets/<dataset>/README.md` : documentation technique de chaque source.
- `reports/datasets/` : rapports d'audit datés et versionnés.
- `reports/generated/` : figures et rapports régénérables, non versionnés.
- `tests/` : tests automatisés.

Voir [l'index de documentation](docs/README.md) et [l'index des rapports](reports/README.md).

## Installation

**Prérequis :** Conda (Miniconda ou Anaconda).

Vérifier l'installation :

```bash
conda --version
```

Créer puis activer l'environnement défini dans `environment.yml` :

```bash
conda env create -f environment.yml
conda activate swiss-votes-ml
```

Pour mettre à jour un environnement existant :

```bash
conda env update -f environment.yml --prune
conda activate swiss-votes-ml
```

L'option `--prune` supprime les paquets absents de `environment.yml`.

## Données et reproductibilité

Les données brutes et les caches ne sont pas versionnés : ils doivent être récupérés ou reconstruits à l'aide des scripts du projet. Des **snapshots `processed` validés et utiles au travail d'équipe** peuvent être conservés sous `data/processed/<dataset>/`.

Le snapshot des explications du Conseil fédéral est disponible dans `data/processed/federal_explanations/`. Pour son contenu, ses limites et sa reconstruction, voir la [documentation du dataset](docs/datasets/federal_explanations/README.md).

## Collaboration

Le développement se fait par branches, avec des pull requests et des revues avant les intégrations importantes. Les analyses, sources, décisions méthodologiques et limites doivent rester traçables dans le dépôt.
