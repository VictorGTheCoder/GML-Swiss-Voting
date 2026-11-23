# V5 — Enrichissement historique des effets du « oui », 23 novembre 2026

## Résultat scientifique et décision

**80 votations supplémentaires de 2005 à 2015 ont été décrites**, avec
**81 effets politiques distincts** issus de **33 groupes de publications
officielles de la Chancellerie fédérale**. Cette acquisition vient compléter
les 42 annotations de V4, sans modification des résultats de votations ou
des sondages.

**L'objectif de MAE ≤ 4 points de pourcentage n'est pas atteint.**
La meilleure variante demeure le candidat de référence V3 :
**7,618292700184025 points** avec les sondages élargis et la tendance
gelée. La meilleure nouvelle variante (mécanismes génériques seuls)
donne **7,626471087954747**, un écart de **+0,00818 point**.
Aucune nouvelle architecture n'est promue.

## 1. Acquisition et vérifications

### Couverture

| Mesure | Avant V5 | Après V5 |
| --- | ---: | ---: |
| Objets historiques 2005–2015 annotés | 0 | **80** |
| Effets distincts décrits durant 2005–2015 | 0 | **81** |
| Groupes de sources officielles pour ces objets | 0 | **33** |
| Fiches V4 2016–2025 conservées | 42 | 42 |
| Objets disposant de tags utilisables, sur 380 | 42 | **121** |
| Objets 1990–2015 annotés dans le train 2016 | 0 | **79** |

L'objet 5340 est conservé dans le jeu historique avec un niveau
de confiance moyen, mais **n'est pas utilisé comme annotation certaine**.
Les 42 fiches V4 restent intactes. Les 258 objets encore sans
annotation et l'objet incertain portent explicitement
`coarse_documented=0` : *inconnu* ne veut pas dire vote sans effet.

Le [catalogue historique Swissvotes](../../../scripts/modeling/historical_objects_v5.py)
a identifié les **240 objets 1990–2015** sans regarder leurs résultats.
Les identifiants et dates des 80 objets du nouveau jeu sont confrontés
à ce catalogue exact.

Sources primaires : [archive des brochures officielles depuis 1978](https://www.bk.admin.ch/fr/compilation-des-explications-du-conseil-federal-depuis-1978),
expliquant les objets avant le scrutin, et les [résumés officiels par date](https://www.bk.admin.ch/fr/votation-federale-du-9-fevrier-2014).
Les **33 URL source** figurent individuellement dans
[`yes_effects_historical_v5.json`](../../../data/annotations/yes_effects_historical_v5.json).
Les sources historiques utilisées comprennent des brochures PDF et les pages
officielles des scrutins.

**Limite critique :** il s'agit d'une première annotation documentaire,
sans relecture indépendante complète. Les fiches ne constituent pas des
interprétations juridiques certifiées et les éditions PDF disponibles
aujourd'hui ne sont pas authentifiées contre chaque version publiée
avant le scrutin. Les pages PDF exactes non établies restent `null`
plutôt que d'inventer un numéro. Certains objets ont plusieurs
mécanismes, sans les écraser par une catégorie unique. Les sources
incluent des pages de votations contemporaines dont on n'a utilisé
que la description du dispositif, **jamais les résultats**.

### Exemple de nuance

L'extension de la libre circulation des personnes en septembre 2005
(`5190`) comporte deux changements distincts :

- `mechanism_treaty` : extension de la libre circulation ;
- `mechanism_employment_rule` : renforcement des mesures
  d'accompagnement contre la sous-enchère salariale.

Les deux effets sont liés au même objet, mais ne décrivent pas
la même politique. Les initiatives 2012 sur l'épargne-logement
et l'initiative sur les résidences secondaires utilisent elles
aussi des instruments différents.

## 2. Réduire la dispersion des variables

Les 81 nouveaux effets historiques, ainsi que les 45 effets V4,
sont ramenés à quatre familles de facettes **plus fréquentes** :
`domain`, `mechanism`, `direction`, `target`.

On teste séparément les mécanismes seuls (par exemple `taxation`,
`public_finance`, `insurance`, `legal_restriction`, `treaty`)
et toutes les facettes. Seuls les tags présents sur **au moins trois
objets d'entraînement** sont encodés. Le vocabulaire est appris
à nouveau dans chaque fenêtre chronologique. Une feature absente
reste inconnue, jamais étiquetée non-applicable à tort. Un indicateur
`coarse_documented` est ajouté seulement s'il varie dans le
train, pour éviter des colonnes constantes artificielles.

Ces classes sont volontairement plus générales que les instruments
V4, sans inférer d'opinion ni de vote individuel à partir de
l'âge, du statut social ou du territoire.

## 3. Comparaison à sondages identiques

La campagne est contrôlée par
[`experiments/municipal_v5/plan.json`](../../../experiments/municipal_v5/plan.json).
Elle conserve le **même XGBoost avec PCA5, paramètres et période
d'entraînement à partir de 1990**, et l'exacte collecte des sondages
V3 avec les deux vagues, l'ancrage national, la tendance 1,0 et
le plafond de correction ±15 points.

Évaluation **exploratoire** 2016–2022 : **66 objets**, **23 dates
complètes**, **138 868 observations communales**, y compris les
objets sans sondage. Aucune cible 2023+ n'est chargée.
Le runner vérifie que la référence **9,42099474882755
sans sondages** et **7,618292700184025 avec sondages** est
reproduite avant d'accepter une comparaison.

| Variante | MAE sans sondages | MAE avec sondages V3 | Écart à V3 sondée |
| --- | ---: | ---: | ---: |
| V3 originale (`baseline_pca5`) | 9,4210 | **7,6183** | — |
| Thèmes Swissvotes multi-hot (`v3_domain_multihot`) | **9,0457** | 7,6746 | +0,0563 |
| Nouveaux mécanismes seuls (`baseline_coarse_mechanisms`) | 9,4730 | 7,6265 | +0,0082 |
| Toutes les facettes (`baseline_coarse_all`) | 9,7043 | 7,7408 | +0,1225 |
| Thèmes multi-hot + mécanismes (`v3_domains_coarse_mechanisms`) | 9,3655 | 7,7794 | +0,1611 |
| Thèmes multi-hot + toutes les facettes (`v3_domains_coarse_all`) | 9,4741 | 7,8594 | +0,2411 |

Le surcoût positif signifie une dégradation. **Aucune amélioration
établie**. Le meilleur enrichissement a un effet pratiquement nul
sur cette validation.

### Erreurs par fenêtre, avec sondages

| Modèle | 2016–18 | 2019–20 | 2021–22 |
| --- | ---: | ---: | ---: |
| Référence V3 | 8,2214 | 7,4099 | 6,9686 |
| V3 thèmes multi-hot | 8,1895 | 7,4370 | 7,1498 |
| Nouveaux mécanismes seuls | 8,2904 | **7,3202** | **6,9498** |
| Toutes les facettes | 8,4050 | 7,5710 | 6,9955 |
| Thèmes + mécanismes | 8,4466 | 7,3383 | 7,1658 |
| Thèmes + toutes facettes | 8,5578 | 7,4456 | 7,1933 |

Les scores par fenêtre ne reçoivent pas le même poids dans la MAE
globale : celle-ci pèse les **objets** à égalité.

### Évolution de la couverture dans le train

| Fenêtre évaluée | Objets annotés dans le train |
| --- | ---: |
| 2016–2018 | **79** |
| 2019–2020 | **86** |
| 2021–2022 | **95** |

C'est un progrès réel par rapport à la V4, dont la première fenêtre
n'avait aucun exemple sémantique d'entraînement. Mais les labels ne
rendent pas automatiquement XGBoost meilleur ; le signal se recoupe
avec les consignes politiques et les domaines déjà présents.

### Incertitude descriptive

Un bootstrap apparié, **3 000 réplications par dates entières**,
est appliqué au gain `MAE_V3 − MAE_variante` :

| Variante | Gain (pp), positif = progrès | Intervalle 95 % descriptif |
| --- | ---: | --- |
| Thèmes multi-hot | −0,0563 | [−0,1904 ; +0,0794] |
| Mécanismes seuls | **−0,0082** | **[−0,1722 ; +0,1678]** |
| Toutes les facettes | −0,1225 | [−0,3035 ; +0,0642] |
| Thèmes + mécanismes | −0,1611 | [−0,3205 ; −0,0185] |
| Thèmes + toutes facettes | −0,2411 | [−0,4286 ; −0,0741] |

Ce bootstrap décrit des dates **déjà exploitées** dans le développement.
Il ne corrige pas les comparaisons multiples et ne prédit pas l'intervalle
de performance de futures votations. Rien n'indique une voie fiable
vers 4 points sur ces données.

## 4. Reproductibilité et suite

- **105 tests ciblés réussis** avec dépendances de modèles verrouillées.
- [CI du benchmark V5 réussie](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45241043829).
- Artefacts: `manifest.json`, tous les scores par objet/date,
  toutes les prévisions communales et le bootstrap apparié, disponibles
  via l'exécution GitHub.
- Sources, code de conversion, plan, manifestes, fichiers d'entrée et
  prédictions protégés par empreintes SHA-256.
- Les objets 2023–2025 et la capture prospective V2 du 29 novembre
  2026 restent intactes.

**Recommandations suivantes :** poursuivre la relecture humaine des
121 fiches ; obtenir des labels plus homogènes avant 2005 ;
analyser les erreurs résiduelles des **objets sans sondage** et les
interactions entre mécanisme et exposition communale
(logement, revenu, secteur agricole). Il faut éviter de relancer
des dizaines de variantes sur les mêmes 23 dates dans l'espoir
d'atteindre artificiellement 4 points.

Voir le [guide V5](../../../docs/project/semantic_v5.md) et
la [PR #78](https://github.com/VictorGTheCoder/GML-Swiss-Voting/pull/78).
