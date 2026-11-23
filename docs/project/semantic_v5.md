# V5 — Enrichissement historique des effets du « oui » (2005–2015)

L'objectif est d'ajouter des exemples **avant 2016** pour les modèles de
votations communales qui utilisent déjà les thèmes politiques et les
sondages nationaux historiques V3. Cette livraison conserve le modèle V3
gelé et sa capture prospective du 29 novembre 2026.

## Documents et représentation

- `data/annotations/yes_effects_historical_v5.json` : **80 objets de
  2005–2015, 81 effets, 33 groupes de documents fédéraux**. Chaque entrée
  conserve `vote_id`, date, URL officielle Chancellerie, note factuelle,
  domaine, mécanisme, sens de la mesure et destinataires directs. Lorsqu'une
  page précise est disponible elle figure dans `source_section_page`.
  Les autres entrées utilisent une page officielle de votation et la page
  imprimée reste inconnue (null).
- Les **42 annotations existantes de V4** sont utilisées sans modification.
- Une fiche historique (`5340`) reste incertaine et n'est pas transformée
  en feature. Total attendu : **121 objets disposant d'étiquettes** sur
  380 objets du jeu préparé (79 historiques + 42 V4).
- `scripts/modeling/historical_objects_v5.py` reproduit le catalogue
  Swissvotes de 1990–2015 **sans lire les résultats** ; l'inventaire comporte
  240 objets dont 80 possèdent une annotation historique V5.

Les annotations historiques sont **une première lecture documentaire**.
Elles ne sont **ni relues par une deuxième personne, ni garanties conformes
à la version historiquement diffusée des brochures**. Les métadonnées
`published_at_verified` sont nulles. Le statut reste
**`strict_forecast_ready=false`**.

## Éviter des dizaines de nouvelles catégories

`scripts/modeling/semantic_labels_v5.py` regroupe les effets directs en
familles plus générales, par exemple `taxation`, `public_finance`,
`insurance`, `treaty`, `legal_restriction`, `migration_rule`,
`rights`, `employment_rule` et `institutional`.

Il garde quatre facettes séparées, sans attribuer d'idéologie ou de
comportement individuel :

- `domain_...` : champ de politique publique affecté ;
- `mechanism_...` : mécanisme juridique concret et généralisable ;
- `direction_...` : sens de modification de la quantité décrite ;
- `target_...` : bénéficiaires ou groupes soumis à la règle.

Les valeurs nominales et les directions ne sont pas interprétées comme des
nombres ordonnés. Des exemples similaires de 2005 et 2014 peuvent ainsi
partager un mécanisme sans nécessairement partager une issue électorale.
Les domaines Swissvotes existants sont comparés séparément pour éviter de
confondre changement de taxonomie et effet des annotations.

Une absence d'annotation reste **inconnue** et non « aucune modification ».
Le vocabulaire des labels est créé sur les **objets d'entraînement seulement** ;
seuls les labels présents sur au moins trois objets de train sont conservés.
Les tags plus rares ne sont pas considérés comme de fausses observations.

## Validation et comparaison

La campagne est décrite avant les scores dans
`experiments/municipal_v5/plan.json` et se reproduit par :

```bash
python -m scripts.modeling.municipal_v2 prepare \
  --output reports/generated/municipal_v5_base

OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 \
python -m scripts.modeling.semantic_training_v5 \
  --base reports/generated/municipal_v5_base \
  --output reports/generated/municipal_v5_historical_semantics
```

Les six variantes évaluent les mécanismes seuls ou avec toutes les facettes,
sur le modèle V3 original ou avec les thèmes Swissvotes multi-hot.
Référence **MAE V3 7,618292700184025** avec la collecte élargie de sondages
et les paramètres inchangés de tendance ; le benchmark refuse de comparer
si elle ne se reproduit pas. Fenêtres historiques : 2016–18, 2019–20,
2021–22, avec modèles entraînés seulement sur les objets précédents.

**66 objets, 23 dates, 138 868 observations**, également répartis entre les
variantes. Les objets sans sondage restent présents. Pas de cible 2023+
chargée ou utilisée. La validation a déjà été explorée : les gains éventuels
restent **exploratoires**, aucun choix promu sans nouveaux scrutins prospectifs.

L'expérience conserve les empreintes des sources, code, plan, données,
rapports par objet/date, prédictions complètes et incertitude descriptive
par bootstrap de 23 dates. Le job dédié dans
`.github/workflows/semantic-v5.yml` vérifie aussi les identifiants exacts
et le traitement des catégories manquantes.
