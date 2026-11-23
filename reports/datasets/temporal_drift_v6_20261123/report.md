# V6 — Dérive temporelle et pondération des votations

## Question

Les comportements électoraux évoluent-ils assez pour que les objets récents
doivent recevoir davantage de poids ? Les tendances historiques améliorent-elles
la prévision des contrastes communaux ?

**Aucune des 12 nouvelles variantes ne dépasse la référence V3.**
La MAE minimale de la campagne reste 7,618292700184025 points.
La PCA pondérée produit un petit gain sur l'erreur locale centrée, mais
la précision finale baisse. Aucun candidat promu.

## Protocole fixé avant calcul

- Trois fenêtres de développement identiques à V3 (2016–2018, 2019–2020,
  2021–2022), 66 objets, 23 dates. 240/270/282 objets d'entraînement,
  depuis 1990. Aucun résultat 2023+ chargé.
- Paramètres des six XGBoost, PCA5, sondages étendus et ancre nationale
  inchangés, sauf les variations explicitement déclarées.
- Décroissance exponentielle des poids par objet : w = 2^(-âge / demi-vie),
  demi-vies 2, 5, 10, 20 ans ; normalisation à moyenne 1.
- Taille effective de Kish : (somme w)^2 / somme w^2. Ce n'est pas
  un décompte d'observations indépendantes.
- Tendance calendaire (année fractionnaire) ou bloc historique :
  moyenne du oui et différence entre 0–5 et 5–15 ans, globalement et
  parmi des objets semblables selon les domaines et l'accord des consignes
  partisanes. Mêmes mesures pour l'écart des moyennes communales
  francophones/alémaniques, et deux comptes de support de similarité.
  Les codes OFS de langue sont issus de la typologie rétrospective 2026.
- Toutes les tendances historiques sont calculées uniquement sur des objets
  du train strictement antérieurs à la date cible. Les objets du jour même
  et les résultats de validation sont exclus, même si une date de validation
  précède un autre objet de validation.
- PCA pondérée : centrer les résidus avec la moyenne pondérée, appliquer
  une SVD sur les lignes multipliées par sqrt(w), puis projeter les résidus
  non redimensionnés. Le modèle des coefficients utilise également les poids
  temporels. Comparer à la pondération des têtes seules.
- La MAE locale centrée retire le biais moyen propre à chaque objet :
  c'est un diagnostic utilisant les résultats observés, non un score de
  prévision opérationnel.

## Résultats

| Variante | MAE train structurel | MAE validation structurelle | MAE locale centrée | MAE finale avec ancre |
| --- | ---: | ---: | ---: | ---: |
| V3 référence | 6,0754 | 9,4210 | 5,6986 | **7,6183** |
| Demi-vie 20 ans | 6,2421 | 9,5042 | 5,7133 | 7,6580 |
| Demi-vie 10 ans | 6,4647 | 9,7267 | 5,7646 | 7,7765 |
| Demi-vie 5 ans | 7,3245 | 9,9592 | 5,7916 | 7,9922 |
| Demi-vie 2 ans | 9,9190 | 10,1511 | 5,8944 | 8,2076 |
| Année seule | 5,9471 | 9,5166 | 5,6854 | 7,7044 |
| Tendances historiques | 5,3796 | 9,6670 | 5,9732 | 8,0166 |
| Tendances + poids 20 ans | 5,4806 | 9,7541 | 6,0267 | 8,1062 |
| Tendances + poids 10 ans | 5,7208 | 9,8903 | 6,0864 | 8,1660 |
| Tendances + poids 5 ans | 6,6047 | 10,1164 | 6,1230 | 8,3422 |
| PCA + têtes pondérées 10 ans | 6,4673 | 9,6798 | 5,6886 | 7,7110 |
| PCA + têtes pondérées 5 ans | 7,3435 | 9,8760 | **5,6586** | 7,8917 |
| Tendances + PCA/têtes pondérées 10 ans | 5,7267 | 9,8114 | 5,9572 | 8,0629 |

### Taille effective et sondages

| Demi-vie | Taille effective moyenne des trois trains | Avec sondage (48 objets) | Sans sondage (18 objets) |
| --- | ---: | ---: | ---: |
| Uniforme | 264,00 | 7,1696 | 8,8147 |
| 20 ans | 242,72 | 7,1649 | 8,9728 |
| 10 ans | 196,38 | 7,2292 | 9,2358 |
| 5 ans | 119,72 | 7,2309 | 10,0224 |
| 2 ans | 49,67 | 7,3652 | 10,4541 |

Bootstrap apparié descriptif par date du gain référence moins variante :
20 ans [-0,1807 ; +0,1052] ; 10 ans [-0,3419 ; +0,0213] ;
5 ans [-0,7989 ; +0,0245] ; 2 ans [-1,2413 ; -0,0271].
Cette comparaison est exploratoire, sur des dates réutilisées, sans
correction des comparaisons multiples.

## Interprétation

Les données anciennes restent utiles au modèle structurel, particulièrement
aux objets dépourvus de sondage. Réduire leur poids diminue la taille
effective de train déjà faible. Le bloc de tendances baisse la MAE train
mais augmente la MAE validation : compatible avec un surapprentissage et
avec un signal historique insuffisamment transférable. Une moyenne globale
des votes passés peut dépendre du mélange des objets proposés, plutôt
que d'un changement de préférences ; les similarités choisies sont grossières.
Les arbres n'extrapolent pas naturellement une tendance calendaire au-delà
des valeurs apprises.

La PCA et les têtes pondérées à 5 ans réduisent l'erreur locale centrée
de 0,0400 point vs la référence et l'erreur des 48 objets sondés
de 0,0423 point, mais font remonter la MAE finale de 0,2734.
Cela motive une hypothèse distincte : pondérer seulement les profils locaux,
tout en gardant un modèle global nourri par l'ensemble du passé.
Cette dernière configuration n'a pas été testée dans V6 et ne doit
pas être présentée comme un résultat.

L'expérience étendue #80 (profondeurs 12, 16 et non limitée, 2 400 arbres)
n'améliore pas le meilleur checkpoint de 7,6063. Cette observation
renforce l'intérêt d'un modèle local avec des variables objet × commune.
Les hyperparamètres, le bloc temporel et les sondages restent des axes
à valider chronologiquement, sans retoucher le test déjà exposé.

## Reproduction

- [PR #81](https://github.com/VictorGTheCoder/GML-Swiss-Voting/pull/81)
- [Campagne, trois jobs réussis](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45278808016)
- [Poids](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45278808016/artifacts/14869235032)
- [Tendances](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45278808016/artifacts/14868152649)
- [PCA pondérée](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45278808016/artifacts/14867832747)

Les quatre tests ciblés réussissent sous l'environnement verrouillé.
Un test de reconstruction a nécessité une copie explicite du tableau
NumPy pour compatibilité avec pandas en lecture seule dans l'environnement
général ; le correctif ne modifie pas les calculs du benchmark.
Les modèles et la capture prospective restent inchangés.
Statut : strict_forecast_ready=false.
