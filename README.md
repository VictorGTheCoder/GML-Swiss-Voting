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
- `reports/` : audit OFS, journaux de nettoyage, validation et diagnostic de jointure.

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

La dépendance `tabulate`, utilisée pour les rapports Markdown, est incluse dans `environment.yml`. Mettre à jour l'environnement existant avec la commande de la section Setup.

Vérifications locales, sans téléchargement :

```bash
python -m pytest tests -q
python -m ruff check scripts tests
```

## Development

Le développement se fait par branches, avec des pull requests avant toute intégration importante.
