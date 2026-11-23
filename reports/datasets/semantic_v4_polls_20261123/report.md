# Comparaison V4 sémantique + sondages historiques V3 — 23 novembre 2026

## Résultat

La comparaison **applique les mêmes sondages nationaux enrichis** aux six
modèles, avec la **même correction de tendance V3** et les mêmes prédictions
structurelles entraînées dans les fenêtres de développement (pas de sondage
utilisé pour réajuster les paramètres XGBoost).

**Le meilleur modèle reste la référence V3 à 7,6183 points de MAE.**
L'intégration des annotations V4 *ne progresse pas* sur les 66 objets
de développement. Le score sans sondages de 9,12 évoqué dans le rapport
V4 précédent n'était **pas comparable** à la MAE avec sondages de 7,62.

Le candidat V2 gelé et les prévisions du 29 novembre 2026 ne sont pas modifiés.

## Comparaison strictement appariée

Population identique pour toutes les variantes : **66 objets, 23 dates complètes,
138 868 lignes commune × objet, 2016–2022**. Les modèles sont entraînés sur les
scrutins antérieurs de 1990 jusqu'à chaque début de fenêtre. Aucune cible
2023 et ultérieure n'est lue. Les **48 nouveaux sondages historiques** de V3
(24 objets 2016–2020) complètent le fichier original, avec les mêmes critères
de publication avant la date de prévision. Sondages absents = repli sur le
modèle structurel, et l'objet reste dans la MAE macro.

La référence est **réentraînée dans cette exécution** avec exactement les
paramètres V3; le programme exige de reproduire 9,4210 sans sondages et
7,6183 avec la collecte élargie. Il refuse une comparaison si l'une des
deux références ne correspond pas.

| Configuration | MAE structurelle, pp | MAE avec V3 sondages, pp | Surcoût vs 7,6183 pp |
| --- | ---: | ---: | ---: |
| V3 originale, `baseline_pca5` | 9,4210 | **7,6183** | — |
| V3 thèmes multi-hot `v3_domain_multihot` | **9,0457** | 7,6746 | +0,0563 |
| V4 thèmes canoniques `canonical_leaf` | 9,2144 | 7,9299 | +0,3116 |
| V4 thèmes canoniques + hiérarchie `canonical_hierarchy` | 9,1189 | 7,6796 | +0,0613 |
| V3 thèmes + effets du oui `v3_domain_plus_effects` | 9,1240 | 7,6606 | +0,0423 |
| V4 thèmes canoniques + effets `canonical_leaf_plus_effects` | 9,2768 | 7,9383 | +0,3200 |

Un surcoût positif signifie un modèle moins précis. Le gain de la représentation
des thèmes **sans sondages** ne se transpose donc pas automatiquement à une
amélioration du modèle déjà calibré sur des intentions de vote nationales.

### Contrôle par fenêtre

| Variante | 2016–18 | 2019–20 | 2021–22 |
| --- | ---: | ---: | ---: |
| V3 originale | 8,2214 | 7,4099 | 6,9686 |
| V3 thèmes multi-hot | 8,1895 | 7,4370 | 7,1498 |
| V4 feuilles | 8,5690 | 7,4663 | 7,3627 |
| V4 hiérarchie | 8,2062 | 7,3576 | 7,1823 |
| V3 + effets juridiques | 8,1895 | 7,3532 | 7,1531 |
| V4 feuilles + effets | 8,5690 | 7,4440 | 7,3971 |

Les différences sont variables selon les fenêtres. Le score complet donne
le **même poids à chaque objet**, pas à chaque fenêtre de dates.

### Incertitude descriptive par date

Bootstrap apparié de **23 dates entières**, 3 000 rééchantillonnages, graine
20261123. Pour chaque variante, la quantité est *MAE V3 référence − MAE
variante* : **positive = gain**.

| Variante | Gain (pp) | Intervalle descriptif 95 % du gain (pp) |
| --- | ---: | --- |
| V3 thèmes multi-hot | −0,0563 | [−0,1904 ; +0,0794] |
| V4 thèmes canoniques | −0,3116 | [−0,5058 ; −0,1273] |
| V4 hiérarchie | −0,0613 | [−0,2050 ; +0,0770] |
| V3 thèmes + effets | −0,0423 | [−0,1858 ; +0,0999] |
| V4 canoniques + effets | −0,3200 | [−0,5130 ; −0,1333] |

Ces intervalles **n'attestent pas une généralisation prospective** : mêmes
dates de développement déjà utilisées, seulement 23 groupes, sélection
multiple et absence d'archives historiques certifiées. Les écarts inférieurs
à 0,1 point peuvent être essentiellement du bruit.

## Pourquoi les annotations ne gagnent-elles pas encore ?

Les **42 fiches pilotes** couvrent beaucoup de scrutins récents, mais les
têtes XGBoost de 2016–2018 ne voient **aucun objet annoté dans le train**.
Celles de 2019–2020 n'en voient que **7**, celles de 2021–2022 seulement
**16**, parmi respectivement 240, 270 et 282 objets passés.

La représentation est détaillée (domaine, instrument, direction, quantité,
groupes concernés), alors que les exemples annotés sont très peu nombreux :
les nouvelles colonnes sont souvent rares et leurs interactions difficiles
à apprendre. C'est une **hypothèse plausible**, pas une cause prouvée par ce
benchmark. La correction par sondage national réduit également l'écart
d'erreur globale que pourrait corriger le seul contenu d'un objet.

La bonne suite est d'**annoter des objets avant 2016** sans consulter les
résultats individuels du modèle, de créer des familles de mécanismes plus
fréquentes, et de tester avec une procédure chronologique indépendante.
Une comparaison future devra inclure le sous-ensemble d'objets sans sondage
et les contrastes communaux, pas seulement la MAE totale.

## Traçabilité et vérification

- [PR #77](https://github.com/VictorGTheCoder/GML-Swiss-Voting/pull/77)
  empilée sur [PR #76](https://github.com/VictorGTheCoder/GML-Swiss-Voting/pull/76).
- [Exécution GitHub Actions réussie](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45231176924).
- [Artefact: manifestes, prédictions appariées, MAE par objet et date](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45231176924/artifacts/14847193714).
- Code : `scripts/modeling/semantic_poll_comparison_v4.py`.
- Plan verrouillé : `experiments/municipal_v4/poll_combination_plan.json`.
- Les **83 tests ciblés ont réussi** avant le benchmark. Le programme a
  ensuite reproduit exactement la baseline V3, a imposé les mêmes
  identifiants de communes/objets/cibles et la même disponibilité des
  sondages entre modèles, puis calculé les six scores.

Empreintes SHA-256 des données préparées, du code, du plan, des annotations
et des deux fichiers de sondages conservées dans le manifeste du benchmark.
Le statut reste `strict_forecast_ready=false` et toutes les annotations
doivent encore subir une relecture indépendante. **Aucun modèle n'est promu.**
