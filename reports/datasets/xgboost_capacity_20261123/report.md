# XGBoost : capacité et généralisation — 23 novembre 2026

## Question et résultat

Le modèle V3 avec sondages élargis (7,618292700184025 points de MAE)
et la variante V5 « mécanismes historiques seuls » (7,626471087954747)
ont été soumis au même audit de capacité. **La complexité de l'arbre
n'est pas la principale limitation observée.** À partir de 150–300
arbres, l'erreur d'entraînement continue à baisser fortement mais
la validation structurelle se dégrade et l'erreur locale plafonne.

Le meilleur score ancré exploratoire est **7,6062621139764** en V3
(L2=100, profondeur 6, 600 arbres), un gain de **0,01203 point**.
Ce gain minime ne justifie pas de remplacer la référence. Le meilleur
score V5 est **7,626032044563271** (profondeur 9, 300 arbres).

## Audit du registre V2 et paramètres réellement utilisés

Le registre V2 contient 54 lignes, dont 52 terminées. Neuf lignes
portent sur l'architecture profile avec XGBoost (plusieurs répétitions,
une interruption). Les campagnes V3/V4/V5 ont surtout gardé le même
réglage pour isoler l'effet des nouvelles données.

Réglage de référence : 300 arbres, profondeur 6, learning_rate=0,03,
reg_lambda=26,395956, subsample=0,8, colsample_bytree=0,8,
min_child_weight=1 (défaut), objectif reg:squarederror, PCA5.
`alpha` (Ridge) et `min_samples_leaf` (ExtraTrees) sont des champs du
registre commun **non transmis à XGBoost**. Pour cet audit,
`min_child_weight` est explicitement passé via `model_params`.

## Protocole

Douze configurations fixes par bloc de variables, chacune mesurée
à 30/75/150/300/600 arbres (60 checkpoints × 2 blocs = 120 scores
agrégés, pas 120 recherches indépendantes). Profondeurs
1/2/3/4/6/9 ; L2 1/26,395956/100 ; min_child_weight 1/5/15 ;
learning rates 0,01/0,03/0,1, en variations univariées autour du
réglage gelé. Aucun choix adaptatif après lecture des scores.

PCA5 et prétraitement appris exclusivement sur le train de chaque
fenêtre chronologique. 240/270/282 objets dans les trois trains.
Validation 2016–2018, 2019–2020, 2021–2022 : 66 objets, 23 dates,
138 868 lignes, mêmes cibles et mêmes sondages, aucun résultat 2023+
lu. Les erreurs de train sont **structurelles**, sans ancrage, et
in-sample (PCA et régressions ajustées sur ce train). Les scores train
agrégés pondèrent les fenêtres par nombre d'objets d'entraînement ;
ceux de validation les pondèrent par nombre d'objets évalués.
Les populations train et validation diffèrent temporellement : leur
écart seul ne suffit pas à diagnostiquer le surapprentissage.

Le programme entraîne chaque tête jusqu'à 600 arbres et évalue les
préfixes des boosters. Pour profondeur 6/300 arbres, il vérifie les
prédictions communales contre la classe publique ObjectProfileRegressor,
ainsi que le résultat de l'ancrage rapide contre PollAnchoredRegressor.
Les deux références sont reproduites.

## 1. Nombre d'arbres (profondeur 6, réglages de référence)

| Arbres | V3 train | V3 val. structurale | V3 val. ancrée | V5 train | V5 val. structurale | V5 val. ancrée |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 | 12,6277 | 10,9785 | 8,6626 | 12,6196 | 10,9995 | 8,7062 |
| 75 | 9,5714 | 9,7707 | 7,9093 | 9,5500 | 9,6678 | 7,8686 |
| 150 | 7,5974 | 9,3817 | 7,6747 | 7,5802 | 9,3822 | 7,6793 |
| 300 | 6,0754 | 9,4210 | 7,6183 | 6,0596 | 9,4730 | 7,6265 |
| 600 | 4,8922 | 9,6596 | 7,6318 | 4,8836 | 9,7194 | 7,6423 |

L'amélioration de la MAE train de 7,60 à 4,89 de 150 à 600 arbres,
associée à la remontée de la MAE structurelle de 9,38 à 9,66,
constitue un signe de surapprentissage par augmentation de capacité.
Les sondages masquent une partie de cet effet.

## 2. Profondeur, 300 arbres (V3)

| Profondeur | Train | Validation structurelle | Validation ancrée |
| ---: | ---: | ---: | ---: |
| 1 | 10,5499 | 9,5266 | 7,9135 |
| 2 | 9,3202 | **9,2172** | 7,7376 |
| 3 | 8,1467 | 9,3523 | 7,7124 |
| 4 | 7,2413 | 9,4264 | 7,7264 |
| 6 | 6,0754 | 9,4210 | 7,6183 |
| 9 | 5,4149 | 9,5521 | 7,6125 |

Profondeur 2 améliore le score structurel de référence de 0,2038
point, mais détériore le score final de 0,1193 point. Un réglage
unique des six têtes est potentiellement inadapté : le niveau
global et les contrastes communaux ont des objectifs différents.

## 3. Autres paramètres

À profondeur 6 et 300 arbres :

| Variation | Train V3 | Validation structurelle V3 | Validation ancrée V3 |
| --- | ---: | ---: | ---: |
| L2=1 | 4,5883 | 9,7209 | 7,9146 |
| L2=26,396 | 6,0754 | 9,4210 | 7,6183 |
| L2=100 | 7,9344 | 9,3394 | 7,6347 |
| min_child_weight=5 | 6,9343 | 9,4869 | 7,7605 |
| min_child_weight=15 | 8,1126 | 9,5548 | 7,9849 |
| learning_rate=0,01 | 8,6844 | 9,5445 | 7,8226 |
| learning_rate=0,10 | 4,3820 | 9,9131 | 7,7982 |

L2=100 et 600 arbres donne 7,6063, mais le bootstrap apparié
de 10 000 réplications par dates entières (graine 20261123,
gain référence moins candidat) est environ [-0,104 ; +0,149]
point. Le gain n'est donc pas établi, encore moins après sélection
sur 60 checkpoints. Cette comparaison améliore 26/66 objets.
Les objets avec sondage se dégradent en moyenne de 0,0385 point,
ceux sans sondage s'améliorent de 0,1467 point. Les trois fenêtres
ne gagnent pas toutes.

## 4. Erreur des contrastes locaux

MAE centrée : soustraire le biais moyen de chaque objet de son erreur
communale, **diagnostic rétrospectif**, pas une MAE de prévision.

| Arbres (profondeur 6) | V3 train centré | V3 validation centrée |
| ---: | ---: | ---: |
| 30 | 6,3921 | 6,2695 |
| 75 | 5,6129 | 5,8765 |
| 150 | 5,0632 | 5,7653 |
| 300 | 4,6186 | 5,6986 |
| 600 | 4,3088 | 5,6823 |

La meilleure MAE centrée de toute la grille V3 est 5,6822,
contre 5,6986 pour la référence : la capacité supplémentaire
ne récupère que 0,0164 point de signal local sur ces dates.
La V5 donne le même constat. Le plateau n'est donc pas uniquement
un problème de prédiction de la moyenne globale.
L'analyse #79 avait montré une MAE oracle de reconstruction PCA5
d'environ 3,89 : cela indique un potentiel de représentation, non
une performance prédictive.

## Décision

**Aucun nouveau réglage promu.** Les résultats montrent des
signes de surapprentissage structurel, et un plateau sur les
contrastes locaux. La MAE avec sondages reste autour de 7,61–7,63
pour les meilleurs réglages, très loin de 4. Cette grille n'est
pas exhaustive (interactions entre hyperparamètres, autres
algorithmes et autres représentations restent possibles).

Priorité : dissocier la régularisation et les objectifs de la
tête globale et des têtes locales, apprendre des interactions
objet × commune sur des covariables disponibles avant vote,
et utiliser une vraie validation chronologique interne pour
l'arrêt anticipé et la sélection. Ne pas retuner sur 2023+.
Les dates 2016–2022 sont des dates de développement déjà vues,
pas un test indépendant. `strict_forecast_ready=false`.

## Preuves et reproduction

- [Exécution complète](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45269188839) : les deux jobs V3/V5 ont réussi.
- [Artefact V3](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45269188839/artifacts/14863599004) et [artefact V5](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45269188839/artifacts/14865275419) : courbes, erreurs par fenêtre et par objet, manifeste.
- `python -m scripts.modeling.municipal_v2 prepare --output reports/generated/capacity_base`
- `python -m scripts.modeling.audit_xgboost_capacity --base reports/generated/capacity_base --feature-set v3 --output reports/generated/capacity_v3` (remplacer v3 par v5 pour la deuxième campagne).

Le code de diagnostic ne modifie aucun modèle gelé. Les petites
corrections de lint et de compatibilité du test minimal ne changent
pas le calcul.
