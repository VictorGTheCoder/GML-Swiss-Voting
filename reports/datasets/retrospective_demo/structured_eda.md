# Ridge communal : EDA et apports des blocs, 31 octobre 2026

Analyse rétrospective exploratoire du snapshot audité de la démonstration.
Le [notebook](../../../notebooks/modeling/02_structured_eda.ipynb) a été exécuté
sur les données réelles ; le [protocole](../../../docs/project/structured_eda.md)
précise les exports, unités et limites. Les scores publiés du Ridge historique
et du Ridge combiné sont reproduits.

L'EDA et tous les ajustements portent sur 2012–2020 : 174 571 observations,
83 objets, 30 dates. La validation réutilisée 2021–2022 comprend 50 520
observations, 24 objets sur sept dates. Aucun résultat du test 2023–2025
n'est chargé ou évalué. Alpha = 1 pour toutes les configurations ; aucun réglage
ni aucune sélection de variables. La cible est la part de oui communale.

## Qualité des variables sur l'entraînement

`party_share_centre` est entièrement manquante. Les domaines d'objet secondaires
présentent aussi une forte absence : 27,71 % pour `object_domain_2` et 85,54 % pour
`object_domain_3`. Parmi les parts de partis, PEV manque sur 23,80 % des lignes,
PBD sur 17,09 % et PVL sur 15,37 %. Ces absences sont décrites explicitement,
sans les remplacer par des zéros dans l'EDA ni décider de nouvelles suppressions.

Les corrélations entre variables et avec la cible sont exportées sur
l'entraînement uniquement. Les codes nominaux sont exclus de ces corrélations.
Les parts d'âge ont des dépendances structurelles ; notamment, les 80 ans et plus
sont inclus dans les 65 ans et plus. Une corrélation forte ne constitue pas à
elle seule un motif de retrait.

## Comparaisons mesurées

Même prétraitement ajusté sur l'entraînement et mêmes clés de validation pour
toutes les configurations ; les observations manquantes sont imputées, sans
suppression de lignes. Les prédictions sont bornées à [0, 1].

| Configuration | MAE communale (points) | Δ vs historique complet (points) |
| --- | ---: | ---: |
| Historique publié | 13,042580 | −0,000264 |
| Historique complet | 13,042844 | 0,000000 |
| Historique complet + démographie | 13,022222 | −0,020621 |
| Historique complet + partis | 13,154591 | +0,111747 |
| Historique complet + typologies | 13,136385 | +0,093541 |
| Historique complet + caractéristiques d'objet | 10,707049 | −2,335795 |
| Combiné publié | 10,697160 | −2,345683 |

L'historique complet ajoute le nombre d'objets historiques à la référence publiée,
qui utilise seulement la moyenne historique et son indicateur d'absence. Cet ajout
est présent dans toutes les comparaisons par blocs et dans le combiné, ce qui
permet d'attribuer chaque delta au bloc ajouté plutôt qu'à une différence
implicite de représentation historique.

Les caractéristiques d'objet apportent l'essentiel du gain observé dans ces
comparaisons d'ajouts à l'historique. Le combiné améliore ce résultat d'environ
0,010 point seulement. Cela ne démontre pas que les autres blocs sont inutiles :
les effets de retrait de chaque bloc du combiné n'ont pas été mesurés.

Le combiné améliore l'historique complet sur **15 objets sur 24** et **six dates
sur sept**. Les deltas par objet vont de −19,383 à +8,976 points ; ceux par date
de −7,368 à +7,628 points. Le gain moyen masque donc des échecs importants.
Les tables exportées détaillent chaque configuration par objet et par date.

## Figures disponibles

L'exécution produit dix figures en PNG et SVG dans
`reports/generated/structured_eda/` : manquants, distributions, modalités,
corrélations numériques, scatters avec la cible, boxplots par typologie,
relations avec les métadonnées d'objet, coefficients du combiné, MAE par
configuration et deltas appariés du combiné.

Les modalités et relations propres à l'objet comptent une fois chaque objet.
Les autres descriptions portent sur les lignes commune × objet. Les coefficients
numériques standardisés, modalités one-hot et indicateurs d'absence sont
représentés séparément, car leurs échelles diffèrent. Les sorties descriptives
ne déclenchent aucune suppression de variable. L'importance par permutation
reste reportée.

## Portée

Ces résultats reposent sur une validation déjà consultée et sur seulement sept
dates ; ils ne constituent pas une évaluation finale indépendante. La géographie
2026 et les versions historiques non établies des sources limitent leur portée à
l'exploration rétrospective. Aucun effet causal, apport du texte des brochures,
nouveau modèle retenu ou performance de prévision opérationnelle n'est établi.

Environnement d'exécution : Python 3.12.3, pandas 3.1.0, scikit-learn 1.9.1.
Les empreintes des entrées et des implémentations ainsi que les configurations
figurent dans le manifeste généré.
