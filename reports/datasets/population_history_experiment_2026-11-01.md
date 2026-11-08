# Population depuis 1981 : effet d'un entraînement plus long

Expérience rétrospective du 1er novembre 2026. Validation 2021–2022 déjà exposée,
identique pour tous les modèles ; test 2023–2025 non chargé. Paramètres fixés avant
exécution : Ridge alpha = 1, boosting aux réglages de la démonstration, sans réglage.

## Périodes réellement utilisables

| regime   |   rows |   objects |   dates |   municipalities | first_date   | last_date   |
|:---------|-------:|----------:|--------:|-----------------:|:-------------|:------------|
| recent   | 174571 |        83 |      30 |             2104 | 2012-03-11   | 2020-11-29  |
| extended | 696532 |       332 |     115 |             2104 | 1982-11-28   | 2020-11-29  |

Les stocks commencent en 1981. La sélection supposée au 2 septembre Y+1 impose
un début effectif plus tardif pour les observations commune × objet disposant de
population. Les stocks invalides et correspondances non résolues sont exclus ;
les configurations sans population utilisent aussi cet échantillon, pour maintenir
la comparaison. La couverture et les exclusions sont exportées séparément.

Validation : 50520 lignes, 24
objets, 7 dates. Clés identiques à la démonstration
publiée : True ; clés absentes :
0, nouvelles : 0.

## Scores sur la même validation

Toutes les MAE sont en points de pourcentage ; plus petit est meilleur.

| model                        |    mae_pp |   mean_object_mae_pp |   mean_date_mae_pp |
|:-----------------------------|----------:|---------------------:|-------------------:|
| ridge_history_recent         | 13.042844 |            13.042844 |          13.274468 |
| boosting_history_recent      | 13.643482 |            13.643482 |          13.982658 |
| ridge_context_recent         | 10.692318 |            10.692318 |          10.726734 |
| boosting_context_recent      | 11.745559 |            11.745559 |          12.067374 |
| ridge_population_recent      | 10.694703 |            10.694703 |          10.728259 |
| boosting_population_recent   | 11.764979 |            11.764979 |          12.076927 |
| ridge_history_extended       | 13.006500 |            13.006500 |          13.222796 |
| boosting_history_extended    | 16.219545 |            16.219545 |          16.415184 |
| ridge_context_extended       | 12.689741 |            12.689741 |          12.701372 |
| boosting_context_extended    | 11.682476 |            11.682476 |          11.963247 |
| ridge_population_extended    | 12.690570 |            12.690570 |          12.698718 |
| boosting_population_extended | 11.599275 |            11.599275 |          11.952126 |

## Contrastes appariés

Un gain positif signifie une baisse d'erreur. `longer_history` compare entraînement
long contre récent à variables identiques. `population_block` compare ajout des
deux variables démographiques au contexte, dans le même régime. Le gain principal
pondère chaque ligne commune × objet ; le gain moyen par date pèse chaque date
une fois. Les deltas par objet et date restent disponibles, sans intervalle de
confiance fondé sur des lignes communales supposées indépendantes.

|   mae_pp_candidate |   mae_pp_reference |   gain_pp | contrast                            | candidate                    | reference                  |   mean_date_gain_pp |   positive_dates |   dates |
|-------------------:|-------------------:|----------:|:------------------------------------|:-----------------------------|:---------------------------|--------------------:|-----------------:|--------:|
|          13.006500 |          13.042844 |  0.036343 | longer_history__ridge_history       | ridge_history_extended       | ridge_history_recent       |            0.051672 |                3 |       7 |
|          12.689741 |          10.692318 | -1.997423 | longer_history__ridge_context       | ridge_context_extended       | ridge_context_recent       |           -1.974637 |                3 |       7 |
|          12.690570 |          10.694703 | -1.995867 | longer_history__ridge_population    | ridge_population_extended    | ridge_population_recent    |           -1.970459 |                3 |       7 |
|          10.694703 |          10.692318 | -0.002385 | population_block__ridge_recent      | ridge_population_recent      | ridge_context_recent       |           -0.001525 |                3 |       7 |
|          12.690570 |          12.689741 | -0.000828 | population_block__ridge_extended    | ridge_population_extended    | ridge_context_extended     |            0.002654 |                5 |       7 |
|          16.219545 |          13.643482 | -2.576063 | longer_history__boosting_history    | boosting_history_extended    | boosting_history_recent    |           -2.432526 |                1 |       7 |
|          11.682476 |          11.745559 |  0.063083 | longer_history__boosting_context    | boosting_context_extended    | boosting_context_recent    |            0.104127 |                5 |       7 |
|          11.599275 |          11.764979 |  0.165705 | longer_history__boosting_population | boosting_population_extended | boosting_population_recent |            0.124801 |                4 |       7 |
|          11.764979 |          11.745559 | -0.019420 | population_block__boosting_recent   | boosting_population_recent   | boosting_context_recent    |           -0.009553 |                2 |       7 |
|          11.599275 |          11.682476 |  0.083201 | population_block__boosting_extended | boosting_population_extended | boosting_context_extended  |            0.011121 |                3 |       7 |

## Sources et limites

Les stocks 1981–2009 viennent directement du bilan démographique OFS, Total et
Étranger, sexe Total ; STATPOP fournit 2010–2021. Le bilan ESPOP 2010 n'est pas
confondu avec le stock STATPOP 2010. Les CSV RTS n'entrent pas dans ce modèle.
Les sources officielles complètes sont archivées avec requêtes, dates de collecte
et empreintes. Les effectifs sont sommés avant les parts dans les fusions ; les
scissions et codes non résolus ne sont pas répartis arbitrairement. Les stocks
invalides restent des sorties annuelles explicites et ne déclenchent pas un
retour silencieux à un stock antérieur devenu caduc.

Les caractéristiques sont l'historique de vote, la population totale, la part
étrangère, la langue, l'urbanité et les quatre métadonnées d'objet. Les âges et les
parts partisanes ne sont utilisés dans aucun des deux régimes : nos données
électorales préparées ne remontent pas avant 2011. Recommandations et texte sont
également exclus. Le score du Ridge complet publié (10,697 points) portait sur
un autre ensemble de variables et ne constitue pas le contrôle isolant l'effet
historique. L'historique communal inclut les votes antérieurs à 1981 dans les deux
régimes et n'est pas recalculé en supprimant le passé du régime récent.

La règle septembre Y+1 n'est pas une preuve de publication historique. Les éditions
courantes peuvent intégrer des révisions et la géographie 2026 est rétrospective.
Les limites ESPOP et les anomalies territoriales décrites dans les audits restent
applicables. L'expérience ne rend pas les données admissibles à la V1 stricte et
ne démontre aucun effet causal ni aucune performance finale indépendante.

## Reproduction

```bash
python -m scripts.espop.population_history
python -m scripts.modeling.population_history_experiment
```

Le manifeste et toutes les sorties détaillées sont dans
`reports/generated/population_history_experiment/`. Les tables annuelles et la
table de modélisation sont distinctes, sous `data/interim/population_history/`.
Les snapshots précédents ne sont pas modifiés.

## Vérifications de l’exécution

Les douze modèles sauvegardés reproduisent leurs prédictions brutes sur
500 lignes de validation à 1e-12 près. Les 225 091 lignes communes à la
préparation récente reproduisent exactement les deux variables démographiques,
les typologies et les métadonnées d’objet du snapshot précédent. Les clés de
validation sont identiques aux 50 520 observations de la démonstration.

Les 8 472 stocks des quatre années de contrôle 1981/1990/2000/2009
concordent avec l’audit officiel épinglé, pour le total et les étrangers.

Environnement : python 3.12.3, numpy 2.5.4, pandas 3.1.0, sklearn 1.9.1.

Table SHA-256 : `11679b00d25db6c785a1d50d082fd75aa8c47f7cf924955c0a4ed126ce8652d5`.

- `population_history_experiment.py` : `597804d6bf4165a13bafff0275524de0e18045315e4c378ac8ca53a2ebce3bda`.
- `retrospective_demo.py` : `3f201ce03bb2f6a335d2f8ed09807f0307a149dd06d06c050701e434a9ecd06e`.
- `population_history.py` : `c92c74b781b6ac249c553cc95e2302e7b81e733b24215c41d79cd474fecd7f1a`.
- `audit_reuse.py` : `fa4d8beab3d020584043a06750e5ecab2381723c09eab8724792206920dedb85`.
- `regularized_votes.py` : `80223aa7f449827413871a0d6ac4fd4f497216e730e477228c664d4602a54fc8`.

## Lecture des résultats

L'extension construit effectivement 696 532 lignes d'entraînement sur 332 objets,
contre 174 571 lignes et 83 objets dans le régime récent. Le premier scrutin
exploitable est le **28 novembre 1982** ; les stocks annuels commencent en 1981.
Les contrôles d'échantillon évitent de confondre profondeur historique et ajout
ou retrait de variables. Les résultats suivants concernent la validation
2021–2022 déjà consultée, sans nouvelle optimisation.

- **Ridge avec population et contexte :** 10,694703 points en entraînement récent
  contre 12,690570 avec l'historique étendu, soit une dégradation de 1,995867 point.
  Le contraste sans population est également défavorable, de 1,997423 point.
- **Boosting avec population et contexte :** 11,764979 points en récent contre
  11,599275 en étendu, soit un gain de 0,165705 point. Le gain est positif sur
  quatre dates sur sept ; ce n'est pas une amélioration uniforme.
- **Apport propre de la population :** presque nul pour le Ridge ; pour le
  boosting long, gain de 0,083201 point sur la MAE communale, mais seulement
  0,011121 point sur la moyenne à poids égal par date. Ces petites amplitudes
  ne prouvent pas une amélioration robuste.
- **Historique seul :** prolonger l'entraînement est presque neutre pour le
  Ridge et défavorable au boosting. Plus de données ne suffit donc pas à
  améliorer les modèles fixés ici.

L'expérience ne bat pas la référence publiée à environ 10,697 points avec le
boosting long. Le Ridge réduit récent obtient un score très voisin de cette
référence ; cela ne démontre pas qu'enlever les âges et partis serait toujours
préférable. Aucun des choix ci-dessus n'est confirmé par un test final indépendant.

**Décision :** conserver la préparation historique réutilisable et les résultats,
mais ne pas remplacer les modèles précédents par le simple entraînement long.
L'hypothèse d'une évolution des relations politiques au fil des décennies peut
motiver plus tard des fenêtres glissantes ou une pondération de récence ; ces
explications et variantes n'ont pas été testées ici.

Protocole et reproduction : [guide](../../docs/project/population_history_experiment.md).

Vérification du code : suite complète **284 tests réussis**, contrôle Ruff et
`git diff --check` réussis. Le SHA-256 du snapshot de modélisation précédent reste
identique à sa référence épinglée. Le test réservé n'a pas été évalué.
