# Interactions objet × commune et profils latents

Protocole fixé le 1er novembre 2026, avant exécution, à partir des
[études comparables](../../reports/datasets/comparable_voting_studies_2026-11-01.md).

## Comparaisons prévues

Même snapshot, mêmes clés et fenêtres annuelles internes 2016–2020 que la
[comparaison par blocs](block_selection.md). Entraînement croissant depuis 2012,
historique pré-2012 inclus et gelé à chaque coupure. Aucun chargement de cible
après 2020. Ces fenêtres ont déjà servi à explorer et restent exploratoires.

- Ridge historique et Ridge combiné, alpha = 1.
- Ridge combiné avec interactions : forme juridique et domaine principal
  croisés avec historique moyen, parts PLR/PS/UDC/Verts, langue et urbanité.
  Imputation, standardisation et vocabulaires appris uniquement dans le train.
- Ridge combiné + recommandations nationales seules, puis + huit interactions
  entre la consigne et la force locale du parti correspondant. PLR/PDC/PS/UDC/
  PEV/Verts/PVL/PBD restent distincts ; pas de fusion PDC/PBD/Centre.
- HistGradientBoosting combiné, puis avec recommandations : mêmes paramètres
  fixés que la démonstration, aucun réglage ni early stopping.
- Modèle au niveau objet : prédiction de sa moyenne communale avec métadonnées
  et recommandations, Ridge alpha = 1. Variante avec trois facteurs territoriaux
  obtenus par SVD de la matrice train objet × commune, centrée par objet. Les
  coefficients sur ces facteurs sont ensuite prédits depuis les métadonnées et
  consignes du nouvel objet. Aucun résultat de ce nouvel objet n'est nécessaire.
  La moyenne réelle d'un objet évalué ne sert jamais d'entrée. Ce niveau est une
  moyenne communale non pondérée, pas la part nationale pondérée par bulletins.

Les prédictions de chaque modèle sont bornées à [0, 1]. Comparaisons appariées
au Ridge combiné par objet/date/fenêtre, MAE en points, résumé à poids égal par
fenêtre et par date. Aucun choix automatique de modèle ni de variables. Pas de
recherche d'hyperparamètres sur les cinq fenêtres. Les dimensions SVD et paramètres
sont fixés ; ils ne sont pas choisis à partir des nouveaux scores.

## Recommandations et limites

Les seules nouvelles colonnes lues sont `p-fdp`, `p-cvp`, `p-sps`, `p-svp`,
`p-evp`, `p-gps`, `p-glp`, `p-bdp`, avec jointure exacte par `vote_key` et
contrôle des dates. Les recommandations cantonales dissidentes ne sont pas
modélisées ici. Les codes catégoriels restent distincts : 1 oui, 2 non, 3 décision
de ne pas donner de consigne, 4 bulletin blanc, 5 liberté de vote, 8 préférence
contre-projet, 9 préférence initiative, 66 neutralité historique, 9999 organisation
inexistante ; les valeurs inconnues restent absentes. Interactions numériques :
force locale × (+1 pour oui, −1 pour non, 0 pour 3/4/5/66), valeur manquante pour
8/9/9999 ou consigne inconnue. Le modèle conserve aussi les catégories originales
et les indicateurs de valeurs manquantes. Source :
[codebook Swissvotes, pages 21–22](https://swissvotes.ch/page/dataset/codebook-de.pdf).

Ces codes proviennent de l'édition actuelle de Swissvotes. Aucune date de
publication historique des consignes n'est prouvée ; la disponibilité avant
scrutin est une hypothèse rétrospective, jamais une validation V1 stricte. La
même limite sur la géographie fixe 2026 et les versions des sources persiste.

## Texte des brochures

L'expérience d'analogues textuels est signalée comme non exécutée si le snapshot
ne fournit pas de correspondance validée entre objet et section. Ne pas joindre
arbitrairement une brochure complète à tous ses objets ; réutiliser les
[contrôles existants](forecast_text_export.md) avant toute future comparaison.

## Reproduction

Dans l'environnement de la démonstration :

```bash
python -m scripts.modeling.interaction_experiment
```

Sorties régénérables : `reports/generated/interaction_experiment/`, contenant
prédictions, métriques et gains par fenêtre/objet/date, couverture, manifeste des
paramètres et empreintes, graphiques et rapport. Les résultats mesurés sont
consignés dans `reports/datasets/interaction_experiment_2026-11-01.md`.
