# Sélection par blocs : expérience rétrospective interne

Cinq fenêtres annuelles fixées avant exécution : 2016, 2017, 2018, 2019, 2020.
Entraînement croissant depuis 2012, arrêté avant chaque année évaluée.
Historique antérieur à 2012 inclus, gelé à la dernière date d'entraînement.
Ridge alpha = 1 ; chaque configuration réajuste son prétraitement et son modèle.
Même population et mêmes clés pour toutes les comparaisons, prédictions bornées à [0, 1].
Les résultats 2021–2022 et le test 2023–2025 ne sont pas chargés.

## Gains mesurés

Un gain positif signifie que le bloc est utile : historique − ajout pour `add`,
retrait − combiné pour `remove`. Les moyennes par fenêtre donnent le même poids
à chaque année ; les moyennes par date donnent le même poids à chaque date.
Les minima/maxima décrivent la variation entre fenêtres, sans intervalle de confiance.

| operation   | block      |   mean_window_gain_pp |   min_window_gain_pp |   max_window_gain_pp |   positive_windows |   windows |   mean_date_gain_pp |   positive_dates |   dates |
|:------------|:-----------|----------------------:|---------------------:|---------------------:|-------------------:|----------:|--------------------:|-----------------:|--------:|
| add         | demography |             -0.001023 |            -0.060836 |             0.075879 |                  2 |         5 |           -0.014382 |                7 |      16 |
| add         | object     |             -0.518605 |            -5.648659 |             4.057980 |                  2 |         5 |           -0.904569 |                7 |      16 |
| add         | parties    |              0.091751 |            -0.012675 |             0.206009 |                  4 |         5 |            0.063725 |               11 |      16 |
| add         | typologies |              0.105091 |             0.016674 |             0.176706 |                  5 |         5 |            0.132213 |               11 |      16 |
| remove      | demography |             -0.025314 |            -0.073220 |             0.020182 |                  1 |         5 |           -0.027997 |                6 |      16 |
| remove      | object     |             -0.660039 |            -5.428818 |             3.747179 |                  2 |         5 |           -0.944973 |                6 |      16 |
| remove      | parties    |             -0.128500 |            -0.771978 |             0.170433 |                  2 |         5 |           -0.093956 |                7 |      16 |
| remove      | typologies |              0.021214 |            -0.050007 |             0.061547 |                  3 |         5 |            0.041755 |               12 |      16 |

## Population par fenêtre

|   window |   train_rows |   train_objects |   evaluation_rows |   evaluation_objects | history_cutoff   |   train_dates |   evaluation_dates |
|---------:|-------------:|----------------:|------------------:|---------------------:|:-----------------|--------------:|-------------------:|
|     2016 |        86223 |              41 |             27339 |                   13 | 2015-06-14       |            14 |                  4 |
|     2017 |       113562 |              54 |             14721 |                    7 | 2016-11-27       |            18 |                  3 |
|     2018 |       128283 |              61 |             21040 |                   10 | 2017-09-24       |            21 |                  4 |
|     2019 |       149323 |              71 |              6312 |                    3 | 2018-11-25       |            25 |                  2 |
|     2020 |       155635 |              74 |             18936 |                    9 | 2019-05-19       |            27 |                  3 |

## Portée et suite

Ces comparaisons ne sélectionnent automatiquement aucune variable. Interpréter
ensemble l'ajout et le retrait : un bloc redondant peut aider seul sans aider le
combiné. Les sorties détaillent les erreurs et gains par objet et date, ainsi
que la couverture et les colonnes entièrement manquantes dans chaque ajustement.
La géographie 2026 et les versions historiques des sources non prouvées limitent
l'expérience à l'exploration rétrospective ; la V1 stricte reste inchangée.
Les nombreuses communes ne sont pas autant d'objets indépendants. Les fenêtres
partagent des données d'entraînement et ne sont pas des réplications indépendantes.
Aucun effet causal ni score final de prévision n'est établi.

Les comparaisons concernent le Ridge alpha = 1, pas les performances possibles
d'autres modèles ou réglages. Aucune permutation n'est exécutée ici : il faut
d'abord définir ses échanges admissibles au niveau objet/commune et leurs cutoffs.
Les hypothèses et empreintes figurent dans `run_manifest.json` ; les tableaux,
prédictions et graphiques sont régénérés avec :

```bash
python -m scripts.modeling.block_selection
```

## Lecture des résultats au 1er novembre 2026

- **Typologies :** l'ajout à l'historique améliore les cinq fenêtres, de 0,017
  à 0,177 point, soit 0,105 point en moyenne annuelle. Le gain de présence dans
  le combiné est plus petit (0,021 point en moyenne), positif sur trois années
  sur cinq et douze dates sur seize. C'est le signal le plus régulier pour
  l'ajout, avec une amplitude faible.
- **Partis :** l'ajout gagne 0,092 point en moyenne, positif sur quatre années.
  Leur présence dans le combiné perd en moyenne 0,128 point : ils n'apportent
  pas le même bénéfice selon les autres variables disponibles.
- **Démographie :** l'ajout est pratiquement neutre en moyenne (−0,001 point).
  Le retrait du combiné réduit la MAE de 0,025 point en moyenne ; ces écarts
  restent descriptifs et faibles.
- **Métadonnées d'objet :** l'ajout dégrade la MAE de 0,519 point en moyenne
  annuelle, avec des gains allant de −5,649 à +4,058 points. Leur présence
  aide sur deux années sur cinq. L'année 2019 ne comporte que trois objets,
  contre treize en 2016 : la moyenne annuelle ne pondère pas ces années par
  leur nombre d'objets. La moyenne des gains par date est aussi négative.

Le gain des métadonnées d'objet observé sur la validation 2021–2022 déjà exposée
ne se généralise donc pas uniformément à ces fenêtres antérieures. Cela ne
prouve pas que ce bloc est intrinsèquement inutile : composition des scrutins,
encodage et modèle peuvent intervenir. Aucun de ces mécanismes n'est isolé ici.

**Décision méthodologique :** conserver les résultats de tous les blocs et ne
pas figer une liste de variables à partir de leur seule moyenne. Les typologies
constituent une candidate de référence compacte à comparer ultérieurement.
Un éventuel changement de modèle, de réglage ou une permutation devra être
évalué selon un protocole explicite ; cette expérience ne les a pas mesurés.

Protocole : [guide](../../docs/project/block_selection.md).
Sorties détaillées : `reports/generated/block_selection/` (régénérables, ignorées
par Git). Les versions et empreintes exactes sont dans son `run_manifest.json`.

## Empreintes de l’exécution

Environnement : python 3.12.3, pandas 3.1.0, numpy 2.5.4, sklearn 1.9.1.

SHA-256 du dataset : `c8a488826093a53f307af0b4a04627fa6d78118a8ac4b25ca8c8e097fdf8e043`.

- `block_selection.py` : `e57b374979b8d7a43b0b98e0d5836caf90ca3ea3182020ef58487ce481cde270`.
- `retrospective_demo.py` : `3f201ce03bb2f6a335d2f8ed09807f0307a149dd06d06c050701e434a9ecd06e`.
- `regularized_votes.py` : `80223aa7f449827413871a0d6ac4fd4f497216e730e477228c664d4602a54fc8`.
