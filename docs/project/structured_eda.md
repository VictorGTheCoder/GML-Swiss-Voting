# EDA du Ridge et comparaison rétrospective des blocs

Le [notebook](../../notebooks/modeling/02_structured_eda.ipynb) explique le Ridge
existant et compare les apports des sources à l'historique. Il ne sélectionne
aucune variable, ne règle aucun hyperparamètre et ne remplace pas le protocole
strict de prévision. Le [glossaire](../../GLOSSARY.md) précise les unités.

## Reproduction

Utiliser l'environnement `swiss-votes-ml` défini par `environment.yml` et exécuter
toutes les cellules dans l'ordre. Autre possibilité : installer
`requirements-demo.txt` puis `nbformat nbclient ipykernel nbconvert` pour exécuter
et exporter le notebook. Les sources préparées sont déjà versionnées ; aucun
téléchargement ni reconstruction n'est effectué.

Depuis la racine, avec un noyau Python de cet environnement :

```bash
python -m jupyter nbconvert --to notebook --execute \
  --ExecutePreprocessor.timeout=600 \
  --output-dir=reports/generated/structured_eda \
  notebooks/modeling/02_structured_eda.ipynb
```

Le notebook versionné reste sans sorties ; la copie exécutée, les figures PNG/SVG,
les tableaux CSV, les prédictions Parquet et le manifeste sont exportés dans
`reports/generated/structured_eda/`, ignoré par Git. Les fonctions réutilisent le
chargeur audité de la [démonstration](retrospective_demo.md), ses empreintes et son
filtre Parquet excluant les cibles après 2022 avant lecture.

## Décisions retenues

- EDA, associations avec la cible et ajustement : entraînement 2012–2020 uniquement.
- Validation 2021–2022 déjà exposée : comparaisons exploratoires, sans sélection
  supplémentaire ; test 2023–2025 réservé.
- Même Ridge, alpha fixé à 1, prétraitement ajusté sur l'entraînement et prédictions
  bornées à [0, 1]. Toutes les configurations évaluent les mêmes clés, sans exclure
  de ligne selon la couverture d'une source. Couverture et imputation sont distinguées.
- `ridge_history` reproduit la référence publiée. `ridge_history_count` ajoute
  `history_n_objects`, utilisé par le combiné, et constitue la référence commune
  pour l'ajout de démographie, partis, typologies ou métadonnées d'objet. Ainsi, le
  gain d'un bloc n'inclut pas implicitement l'ajout du nombre d'objets historiques.
- Le combiné reproduit toutes les variables du Ridge combiné publié. Les ajouts
  individuels à l'historique ne mesurent pas les effets de retrait du combiné.
- MAE communale principale, MAE moyennes par objet et par date complémentaires.
  Les deltas appariés par objet/date sont exportés pour chaque configuration.
- Importance par permutation reportée : une permutation indépendante des lignes
  pourrait casser les propriétés communes aux observations d'un même objet et
  les dépendances entre caractéristiques.

La consultation répétée de validation interdit d'interpréter les nouveaux
classements comme des estimations finales indépendantes. Aucun modèle n'est
automatiquement retenu à partir de ces résultats.

## Figures et interprétation

Le notebook exporte les taux de valeurs manquantes, distributions numériques,
effectifs des modalités, corrélations de Spearman, scatters et boxplots avec la
cible, coefficients du Ridge, MAE par configuration et deltas du combiné par
objet/date. Les tables conservent les résultats de tous les blocs.

Les codes nominaux ne sont pas corrélés comme des nombres. Les graphiques sur
les métadonnées d'objet comptent chaque objet une seule fois et utilisent sa
moyenne communale non pondérée. Les autres descriptions portent sur les lignes
commune × objet ; leur dépendance ne permet pas d'inférer une significativité
à partir du seul nombre de communes.

Les coefficients numériques sont exprimés pour un écart-type après imputation.
Les modalités one-hot et indicateurs d'absence ont une échelle binaire distincte.
Ils sont représentés séparément ; toutes les modalités sont conservées et aucune
n'est une référence supprimée. Corrélations entre variables, parts d'âge
compositionnelles et régularisation limitent l'interprétation. Les coefficients
décrivent les prédictions avant bornage et n'ont pas de sens causal.

Les partis absents restent manquants dans les données descriptives, puis suivent
l'imputation existante du Ridge. Une variable entièrement manquante ou constante
est signalée sans déclencher une nouvelle sélection. Les parts `80_plus` et
`65_plus` se recouvrent.

La géographie 2026, les versions historiques non démontrées des sources et les
24 objets sur sept dates de validation limitent la portée des résultats à une
analyse rétrospective. L'apport du texte des brochures et les performances
opérationnelles restent hors de cette expérience.
