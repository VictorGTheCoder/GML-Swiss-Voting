# V4 — Thèmes canoniques et effets concrets d'un « oui »

## Objectif

La V3 améliore le score en encodant les domaines Swissvotes comme ensembles, mais
maintient trois champs par niveau (`extra_domain_tokens_1/2/3`). Cette V4
propose une **unique liste de thèmes les plus précis** par objet et une deuxième
liste, indépendante, d'effets juridiques associés à l'acceptation de l'objet.

**Thème ≠ mesure et direction.** Une votation sur l'eau peut conditionner les
subventions agricoles sans interdire les pesticides pour tous. Les thèmes
peuvent se recouvrir ; un objet peut modifier plusieurs règles simultanément.

## Schéma de données

Source des thèmes: `data/processed/municipal_v3/object_features.csv`, elle-même
issue des trois branches `d1/d2/d3` et des niveaux `e1/e2/e3` de Swissvotes.
Le thème canonique est un ensemble **sans ordre ni répétition**, représenté par
les codes les plus spécifiques disponibles. Les parents ne sont pas comptés
deux fois. Attention à la **notation réelle Swissvotes**:

```text
4 -> 4.2 -> 4.24
6 -> 6.1 -> 6.12, avec parfois 6.2 comme thème frère
```

Ces codes sont **des catégories**, pas des valeurs numériques. Les parents sont
reconstruits à la demande pour une ablation hiérarchique, sans réintroduire
les colonnes de position d1/d2/d3. Le vocabulaire et les colonnes multi-hot sont
appris uniquement sur les objets d'entraînement de chaque fenêtre.

Le fichier `data/annotations/yes_effects_v4.json` fournit une première
annotation de **42 votations / 45 effets, issus de 13 brochures officielles**.
Chaque effet contient les facettes ci-dessous:

| Facette | Sens |
| --- | --- |
| `domain` | Domaine abordé par le changement légal, indépendant du thème Swissvotes |
| `instrument` | Instrument juridique précis: taxe, condition de subvention, interdiction, droit, règle de bail... |
| `direction` | Augmentation, restriction, introduction, suppression, etc. **d'une quantité nommée** |
| `quantity` | Ce qui change: éligibilité aux aides, impôt, âge de retraite, pouvoir du bailleur... |
| `targets` | Secteurs ou groupes **directement concernés par la règle**, pas motivations présumées |
| `page` et `note` | Numéro de page imprimé dans la brochure et paraphrase factuelle |
| `conditional_on` | Autre objet dont dépend l'entrée en vigueur, quand cela est indiqué |

La direction est attachée à **une quantité**, jamais à une étiquette
« pour/contre l'environnement » ou une valeur politique inférée. Les champs
`source_review` et `independent_review` sont distincts. **Toutes les fiches
restent en attente de relecture indépendante.**

### Deux objets proches mais différents, 13 juin 2021

- `6410`, initiative « eau potable propre »: conditionne les **paiements
  directs agricoles** à de nouvelles exigences. Encodage
  `instrument_subsidy_conditionality` et
  `signed_direct_payment_eligibility_restrict`. **Aucune interdiction générale
  des pesticides n'est attribuée** à cet objet.
- `6420`, initiative « pesticides de synthèse »: vise une **interdiction
  générale** des pesticides de synthèse et des denrées importées qui en
  contiennent. Encodage `instrument_prohibition` et
  `signed_synthetic_pesticides_ban_introduce`.

Sources: [Explications du Conseil fédéral du 13 juin 2021, pages 4 et 6]
(https://www.bk.admin.ch/dam/fr/sd-web/UxUxfYD5ma0h/2021-06-13_explications_du_conseil_federal.pdf).

### Cas particuliers

- La même votation peut porter sur plusieurs mesures (RFFA 2019; fiscalité du
  logement 2025). Les mesures sont stockées séparément, jamais écrasées par
  une catégorie dominante.
- Les objets AVS liés en 2017 et 2022 conservent une référence explicite à
  l'autre objet. Le modèle reçoit un indicateur « condition liée »; aucune
  hypothèse n'est faite sur l'issue du scrutin lié.
- Les formulations de brochures concernant une solution de repli **en cas de
  rejet** (contre-projet indirect) ne sont pas assimilées à l'effet de « oui ».
- Les objets non annotés ont `semantic_tags=""` et
  `semantic_documented=0`. L'absence de code ne veut jamais dire absence
  d'effet.
- Une catégorie nouvelle en validation n'est pas injectée rétrospectivement
  au vocabulaire: elle devient inconnue pour le modèle entraîné.

## Sources et temporalité

Les 13 PDF officiels sont référencés dans `sources` par leur URL, le
**bouclage éditorial imprimé** lorsqu'il a été contrôlé et la page de l'effet.
L'édition accessible aujourd'hui d'un PDF n'est pas nécessairement une copie
authentifiée de sa diffusion historique. `published_at` est donc **null**
plutôt qu'une date de publication supposée. Les brochures comportent parfois
des explications prospectives; les fiches retiennent uniquement des règles
directes décrites dans le document pré-scrutin, et non les résultats ou
sondages postérieurs au vote.

`source_review=checked_against_prevote_booklet` indique une première lecture
documentaire, **pas un contrôle indépendant ni une certification juridique**.
Les 42 fiches doivent être vérifiées par une seconde personne en confrontant
la paraphrase et le numéro de page au texte de l'objet. Toute erreur sera
corrigée dans une nouvelle version, conservant l'ancienne pour traçabilité.
Statut actuel: **`strict_forecast_ready=false`**.

Le projet suit les résultats **agrégés par commune**, jamais les intentions
des personnes individuelles. Les groupes dans `targets` sont des destinataires
directs de la loi, pas des prédictions de comportement.

## Tester l'apport au modèle (développement uniquement)

Les paramètres de l'expérience reprennent ceux de
`experiments/municipal_v3/plan.json`: entraînement à partir de 1990,
profil PCA5 et XGBoost, mêmes 66 objets / 23 dates de 2016–2022. Toutes les
communes d'une même date restent ensemble. Les cibles de 2023 et après ne
sont **jamais chargées**.

Depuis le dépôt avec les dépendances verrouillées et les sources processed:

```bash
python -m scripts.modeling.municipal_v2 prepare \
  --output reports/generated/municipal_v4_base

OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 \
python -m scripts.modeling.semantic_experiment_v4 \
  --base reports/generated/municipal_v4_base \
  --output reports/generated/municipal_v4_semantics
```

Les cinq ablations sont `v3_domain_multihot`, `canonical_leaf`,
`canonical_hierarchy`, `v3_domain_plus_effects` et
`canonical_leaf_plus_effects`. On compare séparément la représentation et
les annotations. Une hypothèse n'est pas déclarée utile sans résultats
reproductibles; les nouveaux résultats ne sont pas un test indépendant.

Les empreintes du snapshot, des annotations, du code et des paramètres, les
vocabulaires de chaque train et les scores par fenêtre/objet sont conservés
dans le dossier de sortie. Les comparaisons V2/V3 publiées et la capture
prospective du 29 novembre 2026 sont **intactes**.

## Étendre la couverture sans fabriquer des labels

Le jeu de 42 objets est un **pilote**, pas l'annotation exhaustive des 380
objets. Les phases suivantes sont: identifier la brochure correspondant
exactement à l'identifiant/date/question; extraire les passages sur
l'effet de « oui » et non les arguments politiques; créer des propositions;
contrôler leur source et leur page; faire une relecture indépendante; geler
une édition datée; puis seulement entraîner et évaluer. Un mécanisme ambigu
reste **inconnu**. Une direction ne peut être déduite d'un titre abstrait.

La précision sur 2023–2025, déjà explorée, ne peut pas constituer une nouvelle
validation indépendante; une mesure prospective sur plusieurs dates sera
nécessaire pour confirmer le progrès.
