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

### Pipeline OFS et Swissvotes

Un seul pipeline télécharge le cube PX complet OFS et Swissvotes, nettoie et valide
les deux sources, puis prépare et contrôle leur clé de jointure :

```bash
python scripts/run_pipeline.py
```

Pour renouveler les deux sources avant la reconstruction :

```bash
python scripts/run_pipeline.py --force
```

Les fichiers bruts présents sont réutilisés sans accès réseau, sauf avec `--force`.
Le pipeline travaille sur l'historique complet du cube, depuis 1960 ; aucun filtre
2010–2026 n'est appliqué. Swissvotes est téléchargé au format CSV puis nettoyé en
Parquet. Les deux tables et leur correspondance sont prêtes pour une jointure ;
les centaines de colonnes Swissvotes ne sont pas encore recopiées dans chaque ligne communale.

Fichiers produits :

- `data/raw/ofs-votes/px-x-1703030000_101.px` : cube OFS brut et provenance associée.
- `data/raw/swissvotes/swissvotes.csv` : données Swissvotes et provenance associée.
- `data/interim/ofs-votes/votes_all_levels.parquet` : cube OFS mis à plat, tous niveaux territoriaux.
- `data/interim/ofs-votes/votes_communes_clean.parquet` : résultats communaux nettoyés.
- `data/processed/ofs-votes/votes_communes.parquet` : résultats ayant passé la validation.
- `data/processed/swissvotes/swissvotes_clean.parquet` : objets Swissvotes nettoyés, une ligne par objet.
- `data/processed/ofs-votes/vote_crosswalk.parquet` : correspondance vérifiée OFS ↔ Swissvotes, une ligne par objet OFS.
- `reports/` : audit OFS, journaux de nettoyage, validation et diagnostic de jointure générés localement, non versionnés.

Les étapes peuvent se lancer individuellement, **depuis la racine du dépôt** :

```bash
python -m scripts.download.download_ofs_votes
python -m scripts.download.download_swissvotes
python -m scripts.cleaning.parse_ofs_votes
python -m scripts.cleaning.audit_ofs_votes
python -m scripts.cleaning.clean_ofs_votes
python -m scripts.cleaning.validate_ofs_votes
python -m scripts.cleaning.clean_swissvotes
python -m scripts.prepare_join
```

Organisation de `scripts/` :

- `download/` : un téléchargement OFS par cube PX et un téléchargement Swissvotes.
- `cleaning/` : parsing PX, audit, nettoyage et validation.
- `votes_config.py` : chemins, sources et définitions des mesures.
- `vote_keys.py` : normalisation exacte des identifiants des deux sources.
- `prepare_join.py` : contrôle des correspondances, des dates, des types de question et de la cardinalité.
- `run_pipeline.py` : unique orchestrateur, qui appelle les étapes de la chaîne.

Le pipeline historique produit les rapports dans `reports/` et refuse d'écrire le Parquet final si un contrôle bloquant échoue. Les unités spéciales et les questions subsidiaires restent présentes avec leurs indicateurs ; leur exclusion éventuelle dépendra de l'analyse.

### Nettoyage et clé de jointure

La colonne commune `vote_key` est une **chaîne de caractères** : le code OFS est
conservé, et le numéro Swissvotes `anr` est multiplié exactement par 10 avec
`Decimal`. Par exemple, `687` devient `6870` ; `682.1`, `682.2` et `682.3`
deviennent trois clés distinctes. Le [codebook Swissvotes](https://swissvotes.ch/page/dataset/codebook-de.pdf)
définit `anr` comme le numéro de votation OFS ; la représentation multipliée par 10
a été vérifiée sur les codes du cube PX. Les dates et les indicateurs de question
subsidiaire sont contrôlés indépendamment. Aucun rapprochement par titre ou date seule n'est effectué.

Pour Swissvotes, les espaces périphériques et Unicode sont normalisés, les cellules
vides et `.` deviennent nulles. Les codes `0` et `9999` sont conservés selon leur
signification dans chaque variable. La date de votation, la forme juridique,
les nombres de bulletins et les pourcentages nationaux/cantonaux sont typés et contrôlés.
Les autres variables restent des chaînes : leur encodage pour le modèle nécessite
une sélection et une interprétation selon le codebook. Aucune imputation automatique n'est faite.

Les votes futurs de Swissvotes restent présents avec `is_future_vote`. Les anomalies
de comptage et les écarts de pourcentages sont signalés par des colonnes `flag_*`
et détaillés dans `reports/swissvotes_quality_issues.csv` ; les valeurs publiées ne
sont pas remplacées. Un écart de pourcentage peut refléter un dénominateur différent.

`reports/join_preparation.md` résume les contrôles. `reports/join_crosswalk.csv`
permet de vérifier chaque correspondance, et `reports/swissvotes_without_ofs.csv`
liste les objets Swissvotes absents du jeu OFS nettoyé, notamment hors de sa couverture.
Une clé OFS sans correspondance, une date incompatible ou un type de question
contradictoire bloque la publication de la table de correspondance. Les doublons
qui transformeraient la jointure en plusieurs-à-plusieurs sont également bloquants.

Après un pipeline réussi, une jointure sur des **colonnes Swissvotes choisies** utilise :

```python
import pandas as pd

ofs = pd.read_parquet("data/processed/ofs-votes/votes_communes.parquet")
swissvotes = pd.read_parquet("data/processed/swissvotes/swissvotes_clean.parquet")
dataset = ofs.merge(
    swissvotes[["vote_key", "titel_kurz_f", "rechtsform"]],
    on="vote_key", how="left", validate="many_to_one",
)
```

Les résultats nationaux et les variables connues après le scrutin ne doivent pas
être utilisés comme prédicteurs d'un résultat à prévoir avant le vote. Les lignes
signalées et les unités spéciales doivent être traitées explicitement lors du choix
de la population d'analyse. Les sorties d'une exécution antérieure ne sont pas une
preuve de réussite si la dernière commande du pipeline a échoué : consulter ses rapports.

La dépendance `tabulate`, utilisée pour les rapports Markdown, est incluse dans `environment.yml`. Mettre à jour l'environnement existant avec la commande de la section Installation.

Vérifications locales, sans téléchargement :

```bash
python -m pytest tests -q
python -m ruff check scripts tests
```

### Explications du Conseil fédéral

Le snapshot des explications du Conseil fédéral est disponible dans `data/processed/federal_explanations/`. Pour son contenu, ses limites et sa reconstruction, voir la [documentation du dataset](docs/datasets/federal_explanations/README.md).

## Collaboration

Le développement se fait par branches, avec des pull requests et des revues avant les intégrations importantes. Les analyses, sources, décisions méthodologiques et limites doivent rester traçables dans le dépôt.
