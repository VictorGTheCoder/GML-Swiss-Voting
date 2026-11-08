# Âges historiques : dernier recensement sélectionnable

Protocole fixé le 1er novembre 2026, avant entraînement. Cette variante ajoute
les âges ponctuels aux modèles de l'[extension population](population_history_experiment.md).
Elle ne fabrique pas une série d'âges annuels observés entre deux recensements.

## Mesures et sélection

Trois parts : 0–19 ans, 20–39 ans, 65 ans et plus. Pour 1980/1990/2000, lire
les effectifs du classeur OFS déjà archivé et vérifié, raccorder les communes à
la géographie 2026 avec les mutations et snapshots contrôlés, sommer les
effectifs avant de diviser par le total du même recensement. Ne pas diviser les
âges RFP par la population annuelle ESPOP. Refuser les scissions/transferts sans
preuve de répartition et les fusions incomplètes. Conserver les exclusions.

RFP : dates de mesure 02.12.1980, 04.12.1990 et 05.12.2000. Sélection à partir
du **1er janvier Y+3**, hypothèse rétrospective explicite. Les dates de première
diffusion de chaque tableau communal ne sont pas démontrées. Une source officielle
indique que les premiers résultats définitifs du RFP 2000 ont été avalisés en
2002 ; cela ne prouve ni la disponibilité de ce classeur exact ni celle de ses
variables d'âge à cette date. La règle Y+3 n'est donc pas présentée comme preuve.
[Confédération, annonce du RFP 2000](https://www.admin.ch/fr/nsb?id=19916).

Dès le stock 2010, utiliser les trois parts calculées dans STATPOP, avec la
sélection au 2 septembre Y+1 déjà employée dans l'expérience précédente. Les
populations résidante RFP et résidante permanente STATPOP restent distinguées
par la source. À chaque scrutin, sélectionner la mesure la plus récente dont
la date de sélection précède le cutoff (veille du vote), jamais une interpolation
entre deux recensements. La sélection remplace la précédente mesure uniquement
lorsque le nouveau millésime devient sélectionnable.

Chaque commune a une ligne explicite par nouvelle mesure. Une mesure exclue
pour géographie ou effectif invalide reste manquante : elle ne déclenche pas un
retour silencieux à un recensement antérieur. Les lignes sans âge sont conservées
pour la comparaison, avec un indicateur ; imputation ajustée sur le train pour
Ridge, valeurs manquantes natives pour le boosting.

Provenance : année, date exacte de mesure, date de sélection supposée, source,
dénominateur, validité et motif d'absence. Ancienneté en années = durée entre
mesure et veille du scrutin / 365,25 jours. L'année du recensement est conservée
comme métadonnée ; le modèle reçoit l'ancienneté, pas une deuxième variable
redondante de millésime.

## Comparaison fixée

Mêmes 50 520 observations de validation 2021–2022 que l'expérience précédente,
sans suppression selon la présence d'âge. Entraînements récent 2012–2020 et
long depuis la première date exploitable de 1982 jusqu'à fin 2020. Dans chacun,
comparer Ridge alpha = 1 et HistGradientBoosting fixe de la démonstration,
avec et sans le bloc âge : huit ajustements, aucune recherche d'hyperparamètres.

Base identique : historique, population totale, part étrangère, typologies et
métadonnées d'objet. Bloc ajouté : les trois parts d'âge, ancienneté, indicateur
d'absence et source catégorielle. Pas d'âge moyen ni de part 80+ approximés à
partir des classes larges, pas de parts de partis ou de texte. Prétraitements
ajustés dans chaque entraînement ; toutes les communes et tous les objets d'une
date restent ensemble. Aucune cible après 2022 n'est chargée et aucun résultat
de validation n'entre dans l'historique, gelé à fin 2020.

La validation est déjà exposée ; cette comparaison reste exploratoire. La
règle temporelle hypothétique, la géographie fixe 2026 et les éditions actuelles
ne rendent pas les données admissibles à la prévision stricte V1. Les deltas
appariés par objet/date sont descriptifs, sans effet causal démontré.

## Exécution

Après préparation de l'expérience population :

```bash
python -m scripts.espop.census_age_history
python -m scripts.modeling.census_age_experiment
```

La première commande réutilise par défaut
`data/raw/espop_reuse/issue67_2026-10-31` ; `--reference-dir` permet d'indiquer une
autre collecte manifestée. Aucune nouvelle collecte réseau n'est nécessaire ici.
Les mesures sont sous `data/interim/census_age_history/`, les résultats sous
`reports/generated/census_age_experiment/`. La table de modélisation enrichie
est distincte et les données des expériences précédentes ne sont pas modifiées.
