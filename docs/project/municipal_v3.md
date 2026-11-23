# Reproduire l'investigation V3

Cette suite de la V2 enrichit les sources, audite les redondances et compare
six hypothèses à paramètres fixés. Les chiffres et décisions sont dans le
[rapport](../../reports/datasets/municipal_v3_20261123/report.md).
Elle ne remplace pas le candidat gelé ni sa capture de prévision future.

## Installation

Depuis la racine du dépôt, utiliser Python 3.12 et les dépendances verrouillées :

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r requirements-experiments.txt
```

Le collecteur historique a été une acquisition revue dans les publications
primaires. Les faits, correspondances et preuves de source sont versionnés dans
`data/external/polls_historical_v3/`. Aucun scraping actuel n'est nécessaire
pour reproduire les expériences. Une nouvelle collecte doit produire un nouveau
snapshot et conserver son propre état de disponibilité.

## Préparer et contrôler les données

```bash
.venv/bin/python -m scripts.modeling.municipal_v2 prepare \
  --output reports/generated/municipal_v3_base

.venv/bin/python -m scripts.modeling.object_enrichment_v3 \
  --input reports/generated/municipal_v3_base \
  --output reports/generated/municipal_v3_object_rebuild
```

Le deuxième résultat reproduit le CSV versionné dans `data/processed/municipal_v3/`.
Les commandes refusent d'écraser les snapshots existants : choisir un nouveau
dossier si une exécution a déjà été faite. Les hashes des sources, des features
et du code sont conservés.

## Six hypothèses structurelles, puis extension des sondages

```bash
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 \
.venv/bin/python -m scripts.modeling.enrichment_experiment_v3 structure \
  --output reports/generated/municipal_v3_replay

OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 \
.venv/bin/python -m scripts.modeling.enrichment_experiment_v3 polls \
  --campaign reports/generated/municipal_v3_replay \
  --output reports/generated/municipal_v3_poll_replay

.venv/bin/python -m scripts.modeling.summarize_enrichment_v3 \
  --campaign reports/generated/municipal_v3_replay \
  --polls reports/generated/municipal_v3_poll_replay \
  --output reports/generated/municipal_v3_report_replay
```

Le [plan](../../experiments/municipal_v3/plan.json) fixe la période, les six variantes,
les paramètres et quatre comparaisons de sondages. Les modèles utilisent une
observation d'apprentissage par objet. Les dates complètes restent ensemble.
Les cibles 2023 et ultérieures ne sont pas chargées. L'ancrage par sondage
réutilise les prédictions structurelles ; la population d'évaluation ne se
réduit jamais aux seuls objets disposant d'un sondage.

Le runner vérifie les empreintes du dataset, du manifeste, des sondages originaux,
du code et des prédictions mises en cache. La préparation des domaines apprend
son vocabulaire seulement dans le train. Les nouvelles données de procédure
et d'organisations sont expérimentales, sans certification des versions historiques.

## Sensibilité aux dates d'enquête approximées

Après la comparaison des sondages, déclarer puis exécuter les quatre scénarios
de bornes. Le second appel lit les chemins et empreintes du plan créé par le
premier ; il réutilise les prédictions sans réentraîner les modèles.

```bash
.venv/bin/python -m scripts.modeling.poll_timing_sensitivity_v3 declare \
  --campaign reports/generated/municipal_v3_replay \
  --comparison reports/generated/municipal_v3_poll_replay \
  --output reports/generated/municipal_v3_timing_replay

.venv/bin/python -m scripts.modeling.poll_timing_sensitivity_v3 run \
  --output reports/generated/municipal_v3_timing_replay
```

Seuls les 27 milieux d'enquête explicitement approximés sont déplacés.
Le nominal doit reproduire exactement les prédictions de la comparaison.
Les scénarios ne servent ni au réglage des paramètres ni au choix d'une nouvelle
date centrale ; leur plage n'est pas un intervalle de confiance.

## Audits de redondance

```bash
.venv/bin/python -m scripts.modeling.feature_redundancy_v3 \
  --input reports/generated/municipal_v3_base \
  --output reports/generated/municipal_v3_correlation_replay

.venv/bin/python -m scripts.modeling.encoded_redundancy_v3 \
  --input reports/generated/municipal_v3_base \
  --output reports/generated/municipal_v3_encoded_replay
```

Ces audits ne chargent pas la cible. Le premier utilise les unités appropriées
à chaque famille ; le second applique l'imputation, la standardisation et le
one-hot du vrai modèle V2 à une ligne par objet. Les paires fortement corrélées
ne sont pas assimilées à des suppressions sûres pour des catégories futures.

## Vérification

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m pytest \
  tests/test_object_enrichment_v3.py \
  tests/test_feature_redundancy_v3.py \
  tests/test_encoded_redundancy_v3.py \
  tests/test_prototype_profile_v3.py \
  tests/test_enrichment_experiment_v3_review.py \
  tests/test_poll_timing_sensitivity_v3.py \
  tests/test_object_profile_v2.py tests/test_poll_anchor.py -q

.venv/bin/python -m ruff check scripts tests
git diff --check
```

Cette sélection compte 120 tests, tous réussis lors de la livraison.

Les scripts sont isolés de V2. Les fichiers de code et données sources sont
versionnés ; les prédictions municipales complètes sont régénérées dans le
dossier de sortie et reliées aux rapports par leur SHA-256. Les rapports
versionnés fournissent également scores par objet/date, diagnostic oracle
explicitement non prévisionnel, bootstrap descriptif par date et provenance.
