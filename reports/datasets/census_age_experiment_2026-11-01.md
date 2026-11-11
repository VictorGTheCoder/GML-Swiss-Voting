# Âges issus des recensements : intégration et comparaison

Expérience rétrospective du 1er novembre 2026. Les trois parts d'âge 0–19,
20–39 et 65+ sont calculées à partir des recensements OFS 1980/1990/2000,
puis des stocks STATPOP annuels dès 2010. Aucune interpolation entre recensements.
L'âge moyen et la part 80+ ne sont pas approximés.

## Sélection temporelle et géographie

RFP : sélection supposée au 1er janvier Y+3, soit 1983/1993/2003. Cette hypothèse
n'est pas une date de publication attestée du tableau communal. Les stocks
STATPOP sont sélectionnés à partir du 2 septembre Y+1, comme dans l'expérience
population. L'ancienne mesure reste utilisée jusqu'à la sélection d'une nouvelle.
Une nouvelle mesure exclue pour territoire ou effectifs invalides reste manquante,
sans retour silencieux à une ancienne valeur. Les âges utilisent le dénominateur
propre à leur source : population résidante RFP, permanente STATPOP. Les effectifs
des constituants prouvés d'une fusion sont sommés avant le calcul des parts ; les
scissions et allocations non prouvées sont exclues et tracées.

Le modèle reçoit trois parts, l'ancienneté de mesure en années, un indicateur
d'absence et la source. L'année et les dates exactes sont conservées en provenance.
Une part d'âge RFP de 1980 employée en 1985 reste une mesure de 1980, pas une
estimation annuelle de 1985.

## Population et résultats

Huit ajustements, mêmes paramètres que l'expérience population. Ridge alpha = 1,
boosting fixe sans early stopping ; aucun réglage ni sélection automatique.
Prétraitements ajustés sur chaque train. Les valeurs d'âge absentes ne suppriment
aucune observation ; Ridge les impute depuis le train, boosting gère les manquants.

| regime   |   rows |   objects |   dates | first_date   | last_date   |   missing_age_rows |
|:---------|-------:|----------:|--------:|:-------------|:------------|-------------------:|
| recent   | 174571 |        83 |      30 | 2012-03-11   | 2020-11-29  |                  0 |
| extended | 696532 |       332 |     115 | 1982-11-28   | 2020-11-29  |               9738 |

Validation commune : 50520 lignes, 24
objets et 7 dates en 2021–2022, déjà exposée. Les quatre
scores sans âge reproduisent l'expérience précédente à moins de 1e-9 point.
Le test réservé 2023–2025 n'est pas chargé. L'historique des scrutins reste gelé
à fin 2020 dans la validation et inclut uniquement des dates strictement passées
pour chaque ligne d'entraînement.

| model                            |    mae_pp |   mean_object_mae_pp |   mean_date_mae_pp |
|:---------------------------------|----------:|---------------------:|-------------------:|
| ridge_population_recent          | 10.694703 |            10.694703 |          10.728259 |
| boosting_population_recent       | 11.764979 |            11.764979 |          12.076927 |
| ridge_population_age_recent      | 10.675110 |            10.675110 |          10.693996 |
| boosting_population_age_recent   | 11.899330 |            11.899330 |          11.720101 |
| ridge_population_extended        | 12.690570 |            12.690570 |          12.698718 |
| boosting_population_extended     | 11.599275 |            11.599275 |          11.952126 |
| ridge_population_age_extended    | 12.723193 |            12.723193 |          12.712271 |
| boosting_population_age_extended | 11.392809 |            11.392809 |          11.570229 |

## Contrastes appariés

Gain positif = baisse de MAE. `age_block` isole l'ajout des âges et de leur
provenance/ancienneté dans chaque régime ; `longer_history` compare long et récent
à variables identiques. Les moyennes par date pondèrent les sept dates une fois
chacune, à distinguer de la MAE communale. Les effectifs d'objets/dates favorables
ne sont pas un test de significativité.

|   mae_pp_candidate |   mae_pp_reference |   gain_pp | contrast                                | candidate                        | reference                      |   mean_date_gain_pp |   positive_dates |   dates |   positive_objects |   objects |
|-------------------:|-------------------:|----------:|:----------------------------------------|:---------------------------------|:-------------------------------|--------------------:|-----------------:|--------:|-------------------:|----------:|
|          10.675110 |          10.694703 |  0.019593 | age_block__ridge_recent                 | ridge_population_age_recent      | ridge_population_recent        |            0.034263 |                4 |       7 |                 17 |        24 |
|          12.723193 |          12.690570 | -0.032623 | age_block__ridge_extended               | ridge_population_age_extended    | ridge_population_extended      |           -0.013554 |                5 |       7 |                 12 |        24 |
|          12.690570 |          10.694703 | -1.995867 | longer_history__ridge_population        | ridge_population_extended        | ridge_population_recent        |           -1.970459 |                3 |       7 |                  9 |        24 |
|          12.723193 |          10.675110 | -2.048083 | longer_history__ridge_population_age    | ridge_population_age_extended    | ridge_population_age_recent    |           -2.018275 |                3 |       7 |                 10 |        24 |
|          11.899330 |          11.764979 | -0.134351 | age_block__boosting_recent              | boosting_population_age_recent   | boosting_population_recent     |            0.356826 |                3 |       7 |                 14 |        24 |
|          11.392809 |          11.599275 |  0.206466 | age_block__boosting_extended            | boosting_population_age_extended | boosting_population_extended   |            0.381898 |                3 |       7 |                 14 |        24 |
|          11.599275 |          11.764979 |  0.165705 | longer_history__boosting_population     | boosting_population_extended     | boosting_population_recent     |            0.124801 |                4 |       7 |                 14 |        24 |
|          11.392809 |          11.899330 |  0.506521 | longer_history__boosting_population_age | boosting_population_age_extended | boosting_population_age_recent |            0.149873 |                3 |       7 |                 11 |        24 |

## Limites et reproduction

Géographie 2026 et éditions actuelles rétrospectives ; disponibilité historique
des tableaux et hypothèses de sélection non validées pour une prévision stricte.
Les observations communales sont dépendantes, la validation est réutilisée et
aucun effet causal ni résultat final indépendant n'est établi. Les mesures RFP
et STATPOP ne sont pas un même univers statistique. Le contraste concerne tout
le bloc ajouté, y compris source, absence et ancienneté, pas un effet causal des
âges pris isolément. Les âges peuvent être vieux de plus de dix ans avant le
prochain millésime sélectionnable ; la couverture et l'ancienneté sont exportées.

```bash
python -m scripts.espop.census_age_history
python -m scripts.modeling.census_age_experiment
```

Sorties : `reports/generated/census_age_experiment/` ; mesures et table enrichie :
`data/interim/census_age_history/`. Les sources et snapshots précédents restent
inchangés. Les manifestes conservent dates, paramètres, exclusions et empreintes.

## Vérifications de l’exécution

Les huit modèles sauvegardés reproduisent leurs prédictions brutes sur
500 lignes de validation à 1e-12 près. Les empreintes des implémentations
correspondent au manifeste, les quatre références sans âge reproduisent
les scores précédents et aucune ligne de validation n’est supprimée.

Environnement : python 3.12.3, numpy 2.5.4, pandas 3.1.0, sklearn 1.9.1.

Table enrichie SHA-256 : `11d734558d74509eec391d9278f66eef3dfc36bbd3c73de74d9a9a4037d41bc2`.

- `census_age_experiment.py` : `90ec17150c983fb20e7df468ab8ae34ba89b12ab404c99990bd26f68d01cb9c6`.
- `population_history_experiment.py` : `597804d6bf4165a13bafff0275524de0e18045315e4c378ac8ca53a2ebce3bda`.
- `census_age_history.py` : `7d25029eb56d6bae4de5d9781dbd0d312d2f593fa56ea1e9ba1c39fd2e9a90ab`.
- `retrospective_demo.py` : `3f201ce03bb2f6a335d2f8ed09807f0307a149dd06d06c050701e434a9ecd06e`.
- `regularized_votes.py` : `80223aa7f449827413871a0d6ac4fd4f497216e730e477228c664d4602a54fc8`.

## Lecture des résultats

L'intégration fournit effectivement les trois parts historiques, leur année/date
et leur ancienneté. Les couvertures des recensements raccordés retrouvent celles
de l'audit : 2 078 communes en 1980, 2 084 en 1990, 2 097 en 2000. Les mesures
annuelles STATPOP couvrent 2 110 communes par millésime dès 2010. Les seules dates
RFP sélectionnables sont 1983/1993/2003 selon l'hypothèse fixée, pas les dates de
collecte du classeur en 2026.

Le train long conserve ses 696 532 lignes, dont **9 738 sans âge exploitable** ;
4 174 correspondent aux premiers scrutins de 1982, avant la sélection du RFP 1980.
Aucune ligne n'est supprimée pour rendre le modèle enrichi artificiellement plus
favorable. Les 174 571 lignes du train récent et les 50 520 de validation ont
un âge STATPOP exploitable. Dans le train long, les mesures RFP restent celles
de leur recensement, parfois âgées de plus de dix ans avant remplacement.

- **Ridge récent :** MAE de 10,694703 à 10,675110 points, gain faible de 0,019593.
- **Ridge long :** de 12,690570 à 12,723193, dégradation de 0,032623 point.
- **Boosting récent :** de 11,764979 à 11,899330, dégradation de 0,134351 point.
- **Boosting long :** de 11,599275 à 11,392809, gain de 0,206466 point. Ce gain
  bénéficie à 14 objets sur 24, mais seulement trois dates sur sept ; il n'est
  pas uniforme selon le scrutin. Le gain moyen à poids égal par date est de
  0,381898 point.

Avec âge, l'entraînement long du boosting gagne 0,506521 point par rapport au
récent, mais reste moins bon que le Ridge récent sur cette validation. L'ajout
est donc techniquement réalisé sans démontrer de gain général ou important.
Le score du Ridge récent enrichi est très proche de la référence historique
publiée à 10,697 points ; la différence ne constitue pas une confirmation
indépendante et les variables ne sont pas exactement les mêmes que la référence
complète avec toutes ses caractéristiques.

**Décision :** conserver la préparation historique et les variantes avec âge,
sans remplacer automatiquement la référence. L'ancienneté et la source doivent
accompagner toute exploitation des parts. Une future comparaison de fenêtres ou
de pondérations temporelles pourra réutiliser ces mesures ; elle n'a pas été
exécutée dans cette expérience.

Protocole : [guide](../../docs/project/census_age_experiment.md).

Contrôle supplémentaire : les trois parts d’âge et les millésimes STATPOP
reproduisent ceux du snapshot initial sur les 225 091 lignes récentes communes
(entraînement et validation), à 1e-15 près pour les parts.

Vérification du code : **288 tests réussis**, Ruff et `git diff --check` réussis.
Le test réservé 2023–2025 n'a pas été évalué.
