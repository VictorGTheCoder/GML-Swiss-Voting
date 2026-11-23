# Expériences communales V2

Cette expérience compare des modèles capables de prédire la part de « oui »
par commune pour un **nouvel objet de votation fédérale**. Elle ajoute des
informations politiques et des indices sur le sens du « oui », étend
l'historique d'entraînement et conserve un journal reproductible des essais.

L'[annexe méthodologique](municipal_v2_methodology.md) explique les choix
d'outils, les risques de fuite et les limites d'interprétation.

Le protocole est défini dans
[`experiments/municipal_v2/protocol.json`](../../experiments/municipal_v2/protocol.json).
Le statut reste `strict_forecast_ready: false` : les versions historiques des
sources et leurs dates de publication ne sont pas toutes attestées. Les
résultats décrivent donc une expérience rétrospective sur une géographie fixe.

## Objectif et métrique

La cible est `yes_share = votes_yes / (votes_yes + votes_no)`. L'objectif est
une **MAE de 4 points de pourcentage ou moins**. Il s'agit d'une erreur moyenne,
pas d'une erreur maximale garantie pour chaque commune.

La métrique principale, `macro_object_mae_pp`, calcule d'abord l'erreur absolue
moyenne des communes de chaque objet, puis donne le même poids à chaque objet.
Elle évite qu'un objet comportant davantage de lignes domine la comparaison.
Le journal conserve aussi la MAE par ligne et par date, les erreurs par objet,
le quantile élevé des erreurs et la proportion des prédictions à moins de
4 points. Ces mesures ne remplacent pas la métrique de sélection.

## Séparation temporelle

Toutes les communes et tous les objets d'une même date de scrutin restent
ensemble. Le modèle de chaque fenêtre est entraîné uniquement sur des dates
strictement antérieures. L'année de début de l'entraînement fait partie de la
configuration de l'essai.

| Fenêtre | Usage |
| --- | --- |
| 2016–2018 | Validation de développement, entraînement avant 2016 |
| 2019–2020 | Validation de développement, entraînement avant 2019 |
| 2021–2022 | Validation de développement, entraînement avant 2021 |
| 2023–2025 | Comparaison rétrospective après gel de la configuration |

Les résultats de 2023–2025 ont déjà été consultés dans des expériences
antérieures du projet. Cette dernière période **n'est donc pas un test final
indépendant**, même si la V2 impose de figer son choix avant de l'ouvrir.
Aucun test indépendant n'est acquis à ce stade. Les résultats 2026 sont exclus
de l'apprentissage et de cette évaluation ; un lot de prévisions peut en
revanche viser un scrutin futur de 2026 sans en connaître les résultats.

Dans l'entraînement, les historiques communaux utilisent uniquement les dates
passées. Pour toute une fenêtre de validation ou de comparaison, ces variables
sont figées à la fin de l'entraînement : les résultats observés au début de la
fenêtre ne servent pas à prédire sa suite. Un découpage aléatoire des lignes,
ou un découpage temporel qui coupe une date en deux, ne mesure pas le même
problème. Voir la documentation scikit-learn sur la
[validation temporelle et les groupes](https://scikit-learn.org/stable/modules/cross_validation.html).

## Données et sens du « oui »

La préparation repart des tables `processed` OFS, Swissvotes, STATPOP,
élections et typologies. Elle contrôle les clés commune–objet, les
correspondances d'objets et les cibles ; les unités spéciales, questions
subsidiaires et résultats provisoires sont exclus.

Le jeu préparé commence en 1981. Cette profondeur ajoute des objets politiques
différents, mais ne rend pas les caractéristiques anciennes complètes. Les
données démographiques absentes restent manquantes ; une observation récente
n'est pas recopiée artificiellement vers le passé. Les règles de sélection
des années STATPOP et électorales sont documentées dans le manifeste, mais
elles ne prouvent pas la date de publication de chaque valeur historique.
Les communes sont harmonisées selon la géographie du **1er janvier 2026** et
les typologies sont celles du snapshot actuel : ces limites empêchent de
présenter l'expérience comme une reconstitution exacte d'une prévision faite
à l'époque.

Trois blocs de variables sont comparables :

| Bloc | Contenu |
| --- | --- |
| `base` | Historique communal, démographie, forces des partis, contexte territorial, forme juridique et thèmes |
| `political` | Bloc précédent, consignes des partis et institutions, votes parlementaires, thèmes détaillés et interactions avec les forces électorales locales |
| `direction` | Bloc précédent et indices directionnels extraits des titres français |

Les codes politiques suivent le
[codebook Swissvotes](https://swissvotes.ch/page/dataset/codebook-de.pdf).
Une consigne de vote libre, une abstention et une information inconnue ne sont
pas transformées en soutien neutre. Les votes parlementaires sont distingués
des résultats populaires de l'objet. Les éditions actuelles de ces données
décrivent des informations préélectorales, sans certifier leur disponibilité
historique exacte.

Les directions des titres sont des **indices lexicaux expérimentaux**, pas
des annotations juridiques validées. Des règles reconnaissent, par exemple,
une hausse de taxe ou une suppression de redevance. Elles ne consultent ni la
cible ni les consignes des partis. Un titre vague, une négation ambiguë ou des
directions contradictoires restent `NaN`. La valeur zéro est réservée à un
maintien explicitement formulé. Chaque correspondance conserve sa règle et
son extrait justificatif. Les brochures dont la correspondance avec l'objet
n'est pas validée ne sont pas utilisées automatiquement.

## Prétraitement et modèles

Les références sont une constante apprise sur les objets d'entraînement et
l'historique de chaque commune. Ridge, XGBoost et CatBoost sont ensuite
comparés sur les mêmes fenêtres. Dans les modèles sur lignes communales,
chaque objet reçoit le même poids total d'entraînement ; une pondération de
récence peut être déclarée dans la configuration.

Pour Ridge et XGBoost, `ColumnTransformer` et `Pipeline` regroupent imputation,
indicateurs de valeurs manquantes, standardisation, encodage des catégories et
sélection de variables. Tout est ajusté sur le train de chaque fenêtre.
CatBoost utilise son traitement des catégories. Les catégories nouvelles et
les valeurs manquantes suivent les règles du modèle entraîné. Cette séparation
est nécessaire pour éviter les
[fuites pendant le prétraitement](https://scikit-learn.org/stable/common_pitfalls.html).

`SelectKBest` utilise ici `f_regression`. C'est une sélection univariée fondée
sur une dépendance linéaire, qui peut manquer une interaction utile à un
arbre. Le choix `select_k: "all"` sert donc de comparaison ; réduire le nombre
de variables n'est pas un progrès automatique. Le score et le choix de `k`
restent dans le développement, conformément aux principes de
[sélection de variables](https://scikit-learn.org/stable/modules/feature_selection.html).

Une autre famille, `profile`, apprend une ligne par objet. Elle décompose son
résultat en moyenne des communes et écarts locaux, puis apprend des profils
par PCA sur la seule matrice d'entraînement. Les métadonnées de l'objet
servent à prédire sa moyenne et ses coefficients de profil avec Ridge,
ExtraTrees ou XGBoost. La moyenne du nouvel objet est **prédite** ; son résultat
national réalisé n'entre pas dans les données de prédiction. Une commune
inconnue reçoit la moyenne prédite de l'objet.

La famille `hierarchical` est une comparaison supplémentaire : elle apprend
la moyenne de l'objet sur les objets historiques, puis des écarts communaux
signés à partir des caractéristiques locales, avec une fenêtre locale
déclarée. XGBoost, CatBoost et Ridge sont comparés pour cette seconde étape.
Le centrage optionnel retire la moyenne des écarts **prédits**, jamais celle
des résultats futurs. Il nécessite toute la population communale de l'objet
dans le même appel. Cette décomposition est une hypothèse testée ; sa
complexité ne constitue pas une preuve de gain.

## Sondages et horizon de prévision

Si `data/external/polls/srg_gfs_polls.csv` est présent, `prepare` ajoute les
sondages et leur provenance au jeu préparé. La jointure retient la **dernière
vague admissible**, sur l'identifiant exact de l'objet et sa date. La
publication doit précéder le scrutin et ne pas dépasser le cutoff disponible.
Les objets sans sondage restent dans l'évaluation.

La famille `poll_anchor` ajuste un modèle de base vers une estimation issue
du sondage. Les configurations comparent le poids de cet ajustement et
l'allocation des indécis au « oui ». Une autre série teste une tendance
calculée à partir de deux vagues admissibles et extrapolée vers le jour du
vote. Le coefficient `eta` prend les valeurs **0, 0,5 ou 1** ; la correction
de tendance est limitée à **±15 points de pourcentage**. Avec `eta=0`, aucune
extrapolation n'est appliquée. Une vague seule ne suffit pas à déterminer une
pente. Ces variantes sont des hypothèses soumises à validation, sans gain
présumé ni utilisation du résultat final pour choisir la tendance.

La moyenne de référence de l'ancrage est pondérée par un proxy : population
STATPOP × part suisse × part hors 0–19 ans. Ce produit de marges ignore leur
dépendance, les électeurs de 18–19 ans, les expatriés et la participation.
Il ne remplace pas un registre électoral. La moyenne communale non pondérée
reste une mesure séparée.

Une prévision faite quelques jours avant le vote peut disposer d'une seconde
vague de sondage ; une prévision faite plusieurs mois auparavant ne le peut
pas. Les performances doivent donc être rattachées à leur horizon et aux
sources effectivement disponibles. Le backtest utilise son cutoff déclaré ;
une vraie prévision future utilise `as_of`, sans attendre fictivement la veille
du scrutin.

**Contrat de prédiction : fournir le lot communal complet pour chaque objet**
lorsqu'un ancrage national ou un centrage local est actif. Le modèle d'ancrage
contrôle la couverture de population et refuse une commune isolée. Une
requête sur une seule commune ne permettrait pas de calculer le même
ajustement national.

## Lancer et reprendre une expérience

Les commandes suivantes se lancent depuis la racine du dépôt, dans un
environnement Python dédié contenant `requirements-experiments.txt`. Les
tables `data/processed` doivent déjà avoir été préparées par le pipeline du
projet. Le dossier distinct ci-dessous préserve les essais existants.
Les entraînements CPU utilisent deux threads. Pour garder également cette
limite dans les bibliothèques numériques lancées depuis le terminal :

```bash
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
python -m pip install -r requirements-experiments.txt
experiment_dir=reports/generated/municipal_v2_reproduction

python -m scripts.modeling.municipal_v2 prepare --output "$experiment_dir"
python -m scripts.modeling.municipal_v2 baseline --output "$experiment_dir"
python -m scripts.modeling.municipal_v2 run --output "$experiment_dir" \
  --config experiments/municipal_v2/profile_configs.json \
  --hypothesis "Comparer les profils communaux aux régressions par ligne"
python -m scripts.modeling.municipal_v2 leaderboard --output "$experiment_dir"
```

Une configuration JSON peut être un objet ou une liste d'objets. Elle précise
au minimum `name` et `model`, puis éventuellement `blocks`, `train_start`,
`params`, `select_k` ou `half_life_years`. Le fichier de profils fournit des
exemples exécutables.

Les séries complémentaires se lancent avec le même moteur :

```bash
python -m scripts.modeling.municipal_v2 run --output "$experiment_dir" \
  --config experiments/municipal_v2/round2_configs.json \
  --hypothesis "Comparer profils, résidus hiérarchiques et sélection de variables"
python -m scripts.modeling.municipal_v2 run --output "$experiment_dir" \
  --config experiments/municipal_v2/poll_configs.json \
  --hypothesis "Comparer les ancrages sur la dernière vague disponible"
python -m scripts.modeling.municipal_v2 run --output "$experiment_dir" \
  --config experiments/municipal_v2/trend_configs.json \
  --hypothesis "Comparer une tendance atténuée ou complète à aucune extrapolation"
```

Préparer le dossier avec les sources et le code de cette série avant de
lancer les essais. Si le fichier de sondages ou le code change, utiliser un
nouveau dossier et refaire `prepare` ; les empreintes empêchent de mélanger
silencieusement des versions différentes.

```bash
python -m scripts.modeling.experiment_control_v2 tune --output "$experiment_dir" \
  --family xgboost --study-name xgb_search_v1 --trials 12
python -m scripts.modeling.experiment_control_v2 tune --output "$experiment_dir" \
  --family profile --study-name profile_search_v1 --trials 12
```

[Optuna](https://optuna.readthedocs.io/en/stable/faq.html) conserve les études
dans `optuna.sqlite3`. Relancer le même nom d'étude reprend la recherche et
ajoute le budget demandé, à condition que la signature des entrées reste
identique. Les hypothèses et décisions entre familles doivent être notées ;
le programme n'invente pas automatiquement une nouvelle source de données.

Chaque essai possède un `run_id`, sa configuration complète, ses versions de
bibliothèques, les empreintes du code et des données, son hypothèse, son état,
les dates des partitions, les variables retenues et ses métriques. Les
prédictions et erreurs par objet et date sont conservées avec l'essai. Un
échec est également enregistré. Un essai terminé n'est réutilisé que si sa
provenance correspond ; un changement nécessite un nouveau nom ou dossier.

## Geler, comparer et conserver le candidat

Après examen des seules fenêtres de développement, remplacer
`RUN_ID_RETENU` par l'identifiant exact d'un essai terminé :

```bash
python -m scripts.modeling.experiment_control_v2 freeze --output "$experiment_dir" \
  --run-id RUN_ID_RETENU
python -m scripts.modeling.experiment_control_v2 compare --output "$experiment_dir"
python -m scripts.modeling.experiment_control_v2 fit --output "$experiment_dir"
```

`freeze` signe la sélection, les sources, le code et l'environnement.
`compare` enregistre la comparaison 2023–2025, ses prédictions et le modèle
évalué dans `comparison/`. Une comparaison terminée n'est pas rouverte pour
choisir une autre configuration. Son bootstrap rééchantillonne des dates
entières ; il reste descriptif et ne corrige pas l'exposition antérieure de
la période.

`fit` réentraîne les paramètres retenus sur tout l'historique admissible du
jeu préparé. Il produit `candidate_model.joblib` et
`candidate_model_card.json`, séparés du modèle évalué. Ce candidat est
réutilisable pour la recherche ; sa précision après réentraînement n'a pas
fait l'objet d'une nouvelle mesure indépendante. « Final » désigne ici le
candidat retenu pour cette série d'essais, pas un modèle validé pour la
production.

## Enregistrer une prévision avant le scrutin

Après `fit`, le dossier d'expérience contient le jeu historique, le modèle
candidat et sa model card. Exemple pour une capture réalisée le 23 novembre
2026, avant le scrutin du 29 novembre :

```bash
python -m scripts.modeling.forecast_municipal --output "$experiment_dir" \
  --vote-date 2026-11-29 --as-of 2026-11-23
```

`--polls chemin.csv` permet de choisir explicitement le fichier de sondages.
Une date seule dans `as_of` signifie minuit UTC ; un timestamp ISO permet un
cutoff plus précis. Pour un autre scrutin, adapter les deux dates. La commande
refuse une capture après le vote et l'écrasement d'un lot déjà enregistré.

Les communes viennent de la dernière date du jeu historique. Les sources
sont jointes au cutoff `as_of`, puis le modèle prédit en un appel l'ensemble
communes × objets. Aucune cible future n'est créée, et les résultats OFS
courants ne sont pas lus. Les fichiers `forecast_YYYYMMDD.csv`,
`forecast_YYYYMMDD_summary.csv`, `forecast_YYYYMMDD_features.parquet` et
`forecast_YYYYMMDD_provenance.json` conservent les prédictions, les deux
moyennes distinctes, les entrées exactes et les hashes du modèle et des
sources, avec l'heure réelle de capture.

Ce lot permettra une évaluation prospective lorsque les résultats seront
publiés. Sa création ne valide pas encore sa précision et ne change pas le
statut `strict_forecast_ready: false` ni les limites des titres et des
versions historiques.

## Place d'e-means

Le préprint [e-means du 6 novembre 2026](https://arxiv.org/abs/2611.09501)
propose une optimisation du clustering **k-means**, pas un remplacement de
kNN ni un régresseur de résultats électoraux. Il pourrait servir à construire
des groupes de communes ou des distances à leurs centres. Cette piste n'est
pas intégrée à la V2 : il faudrait apprendre ces groupes seulement sur le
train et démontrer un gain de validation. La PCA du modèle `profile` répond
à un autre objectif et n'est pas une implémentation d'e-means.
