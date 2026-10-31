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

Pour reconstruire **toutes les sources** (OFS, Swissvotes, STATPOP, typologies,
répertoire, élections et brochures), puis vérifier leurs formats et identifiants :

```bash
python -m scripts.run_pipeline --all
```

Les sources déjà présentes sont réutilisées. `--force` renouvelle les sources.
STATPOP télécharge un export PX d'environ 153 Mo. Les tables restent séparées ; le
rapport `reports/generated/dataset_compatibility/audit.md` distingue la compatibilité
structurelle de la disponibilité temporelle et des correspondances à valider.
Les tables communales préparées utilisent `municipality_id` au format chaîne OFS
sur quatre caractères. Les élections conservent les valeurs manquantes et n'inventent
pas de date de publication historique.

La pipeline nettoie et valide OFS et Swissvotes dans deux tables distinctes. Elle ne fusionne pas les datasets :

```bash
python -m scripts.run_pipeline
```

Pour renouveler les deux sources avant la reconstruction :

```bash
python -m scripts.run_pipeline --force
```

Les fichiers bruts présents sont réutilisés sans accès réseau, sauf avec `--force`.
Le pipeline travaille sur l'historique complet du cube, depuis 1960 ; aucun filtre
2010–2026 n'est appliqué. Swissvotes est téléchargé au format CSV puis nettoyé en
Parquet. Les deux tables restent séparées. Leur correspondance peut être préparée
explicitement avec `--prepare-joins`, sans recopier les variables entre sources.

Fichiers produits :

- `data/raw/ofs-votes/px-x-1703030000_101.px` : cube OFS brut et provenance associée.
- `data/raw/swissvotes/swissvotes.csv` : données Swissvotes et provenance associée.
- `data/interim/ofs-votes/votes_all_levels.parquet` : cube OFS mis à plat, tous niveaux territoriaux.
- `data/interim/ofs-votes/votes_communes_clean.parquet` : résultats communaux nettoyés.
- `data/processed/ofs-votes/votes_communes.parquet` : résultats ayant passé la validation.
- `data/interim/swissvotes/swissvotes_clean.parquet` : Swissvotes nettoyé complet, toutes les colonnes source conservées.
- `data/processed/swissvotes/swissvotes_clean.parquet` : Swissvotes allégé pour le projet, une ligne par objet.
- `data/interim/integration/ofs_swissvotes_crosswalk.parquet` : correspondance vérifiée OFS ↔ Swissvotes, une ligne par objet OFS, uniquement si la préparation est demandée.
- `reports/` : audit OFS, journaux de nettoyage, validation et diagnostic de jointure générés localement, non versionnés.

Les étapes peuvent se lancer individuellement, **depuis la racine du dépôt** :

```bash
python -m scripts.ofs_votes.download_ofs_votes
python -m scripts.swissvotes.download_swissvotes
python -m scripts.ofs_votes.parse_ofs_votes
python -m scripts.ofs_votes.audit_ofs_votes
python -m scripts.ofs_votes.clean_ofs_votes
python -m scripts.ofs_votes.validate_ofs_votes
python -m scripts.swissvotes.clean_swissvotes
python -m scripts.integration.prepare_join
```

Organisation de `scripts/` :

- `modeling/` : construction des features, modèles Ridge et boosting, expérience textuelle, validation chronologique et métriques.
- `elections/` : collecte des résultats et de la force des partis au Conseil national.
- `ofs_votes/` : collecte PX, parsing, audit, nettoyage et validation OFS.
- `swissvotes/` : collecte et nettoyage Swissvotes.
- `federal_explanations/` : collecte, extraction, audit et export des brochures.
- `repertoire_communes/` : répertoire historique des communes, correspondance de codes et contrôle des codes de votation.
- `statpop/` : population résidante par commune (collecte, conversion Parquet, features démographiques).
- `typologies/` : typologies territoriales et régions linguistiques (collecte, table des communes).
- `common/` : configuration, construction unique des identifiants et utilitaires de collecte PXWeb.
- `integration/` : correspondances, audit de compatibilité et construction explicite de la table exploratoire.
- `run_pipeline.py` : orchestration OFS et Swissvotes ; avec `--with-communes`, répertoire des communes, STATPOP et typologies.

Les modules se lancent depuis la racine du dépôt avec `python -m`, par exemple
`python -m scripts.modeling.evaluate_votes --help` ou
`python -m scripts.elections.collect_elections_conseil_national --help`.
Les notebooks d'exploration sont regroupés dans `notebooks/datasets/<source>/eda.ipynb`
et lisent les tables du pipeline. L'ancienne collecte CSV OFS par API a été supprimée.

La préparation des correspondances est optionnelle :

```bash
python -m scripts.integration.prepare_join
# Ou nettoyage suivi du contrôle des clés :
python -m scripts.run_pipeline --prepare-joins
```

Seuls les identifiants, dates et types de question sont comparés. La table de correspondance est un artefact intermédiaire ; les datasets restent séparés jusqu'à l'intégration des autres sources.

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
dans la table complète `interim/` et détaillés dans `reports/swissvotes_quality_issues.csv` ; les valeurs publiées ne
sont pas remplacées. Un écart de pourcentage peut refléter un dénominateur différent.

La sélection Swissvotes est appliquée automatiquement après le nettoyage : le fichier
`raw/` reste original, `interim/` conserve la table nettoyée complète, et `processed/`
contient la sélection. Les colonnes entièrement nulles, résultats nationaux/cantonaux,
indicateurs de qualité de ces résultats, date d'entrée en vigueur (`dat-force`), liens
documentaires secondaires et doublons `anr`/`datum` sont exclus de `processed/`.
`swissvotes_id`, `vote_key`, `vote_date` et le lien `swissvoteslink` sont conservés.
Les thèmes, recommandations, variables de campagne et champs peu renseignés ne sont
pas exclus automatiquement : aucun seuil de valeurs manquantes n'est appliqué.

Les décisions pour chaque colonne sont enregistrées dans
`reports/swissvotes_column_selection.csv`, avec motif et taux de valeurs manquantes.
Les règles sont dans `scripts/swissvotes/select_swissvotes_columns.py`.
Cette sélection ne constitue pas une liste de prédicteurs prêts à l'emploi : il reste
à vérifier la disponibilité avant la date de prédiction et à encoder les catégories.
La suppression des colonnes vides est recalculée sur chaque nouvelle version des données.

`reports/join_preparation.md` résume les contrôles. `reports/join_crosswalk.csv`
permet de vérifier chaque correspondance, et `reports/swissvotes_without_ofs.csv`
liste les objets Swissvotes absents du jeu OFS nettoyé, notamment hors de sa couverture.
Une clé OFS sans correspondance, une date incompatible ou un type de question
contradictoire bloque la publication de la table de correspondance. Les doublons
qui transformeraient la jointure en plusieurs-à-plusieurs sont également bloquants.

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

La CI exécute la suite complète sur Windows et Linux à chaque pull request.
`ruff.toml` fixe les règles du dépôt ; `requirements-test.txt` définit l'environnement
pip minimal de la CI. L'environnement complet de travail reste `environment.yml`.

### Datasets communaux (STATPOP, typologies, répertoire des communes)

Ces trois sources se construisent à part, sans fusion avec les résultats de votations :

```bash
python -m scripts.run_pipeline --with-communes
```

STATPOP utilise l'export PX complet (environ 153 Mo), puis extrait les années localement ; les fichiers présents sont réutilisés et contrôlés. Le mode API par lots reste disponible comme solution de repli, mais il est beaucoup plus lent. Chaque dataset écrit sous `data/<étape>/<dataset>/` (`repertoire_communes`, `statpop`, `typologies`). Pour leur contenu, leurs règles de disponibilité avant scrutin et leur reconstruction, voir la documentation de [STATPOP](docs/datasets/statpop/README.md), des [typologies](docs/datasets/typologies/README.md) et du [répertoire des communes](docs/datasets/repertoire_communes/README.md).

### Explications du Conseil fédéral

Le snapshot des explications du Conseil fédéral est disponible dans `data/processed/federal_explanations/`. Pour son contenu, ses limites et sa reconstruction, voir la [documentation du dataset](docs/datasets/federal_explanations/README.md).

## Table exploratoire structurée

Après préparation des sources, une étape explicite crée la table rétrospective
commune × objet, sans texte et avec les hypothèses temporelles documentées :

```bash
python -m scripts.integration.build_modeling_dataset
```

Voir [le contrat de la table](data/processed/modeling/README.md). La sortie reste
distincte des sources et du protocole de prévision stricte ; elle ne constitue
pas encore une évaluation de modèle.

## Préparation de modélisation V1

La [V1](docs/project/modeling_v1.md) réutilise les sources préparées pour assembler
30 features candidates avec provenance, contrôles de géographie et de disponibilité,
couverture et exclusions. Elle reste distincte de la table exploratoire ci-dessus.
La commande complète figure dans le guide ; `--source-layout processed` est le
mode par défaut, sans nouveau téléchargement ni harmonisation des sources.
Le snapshot audité est dans `data/processed/modeling_v1/`.

La population strictement admissible reste **vide** : les preuves de publication
historiques manquent et les partitions ne sont pas encore justifiées. Aucun
score réel, entraînement strict ni accès au test final n'est revendiqué.

## Collaboration

Le développement se fait par branches, avec des pull requests et des revues avant les intégrations importantes. Les analyses, sources, décisions méthodologiques et limites doivent rester traçables dans le dépôt.
