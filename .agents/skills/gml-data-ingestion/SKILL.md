---
name: gml-data-ingestion
description: Sécuriser l’import, le nettoyage et la transformation des données des votations fédérales suisses au niveau communal, avec provenance, temporalité et géographie explicites.
---

# Ingestion des données GML

À utiliser pour toute modification d’import, nettoyage, jointure ou transformation des données du projet.

## Contexte stable du projet

- Le projet porte sur l’analyse et la prédiction des **votations fédérales suisses au niveau communal**.
- L’unité d’observation principale est **commune × objet de votation**.
- La target principale est `yes_share = votes_yes / (votes_yes + votes_no)`.
- Le périmètre initial d’analyse est **2013–2024**. La source historique couvre davantage d’années ; ne pas confondre la couverture du cube brut et la période retenue pour une analyse.
- La source centrale des résultats est l’OFS, cube PXWeb `px-x-1703030000_101`, **« Votations populaires — résultats au niveau des communes depuis 1960 »**.

Les sources démographiques et électorales communales étudiées pour d’éventuelles features incluent STATPOP (`px-x-0102010000_101`) et les élections au Conseil national (`px-x-1702020000_105`). Ce sont des sources auxiliaires : vérifier leur millésime, leur géographie et leur disponibilité avant chaque scrutin avant de les joindre.

## Règles d’ingestion et de nettoyage

1. Conserver les fichiers bruts tels que fournis. Enregistrer pour chaque source son identifiant, son URL ou endpoint, sa version/date de mise à jour, la date de collecte et une empreinte (par exemple SHA-256). Une mise à jour de la source doit rester traçable.
2. Préserver les niveaux agrégés et les lignes sources dans les étapes intermédiaires lorsque c’est utile à l’audit. Le dataset communal final ne contient que les observations communales exploitables ; ne pas bâtir la target à partir de lignes cantonales ou nationales.
3. Utiliser `(vote_id, municipality_id)` comme clé du dataset final et vérifier son unicité. Plusieurs objets peuvent être soumis le même jour : parser et contrôler `vote_date`, mais ne pas utiliser la date seule comme identifiant de l’objet.
4. Garder `municipality_id` comme identifiant OFS textuel, avec ses zéros initiaux. Ne jamais joindre uniquement sur le nom de commune. Les codes des unités spéciales de la statistique politique ne désignent pas des communes.
5. Traiter les cellules inconnues ou les marqueurs de valeur indisponible comme manquants, jamais comme zéro. Distinguer explicitement les lignes sans décompte oui/non, les dénominateurs nuls et les autres exclusions métier ; consigner la raison de chaque exclusion.
6. Calculer `yes_share` uniquement lorsque `votes_yes` et `votes_no` sont disponibles et que leur somme est strictement positive. Après nettoyage, contrôler les comptes non négatifs et `yes_share ∈ [0, 1]`.
7. Conserver les indicateurs qui changent l’interprétation, notamment les résultats provisoires et les questions subsidiaires. Une question subsidiaire ne représente pas une approbation simple de l’objet ; l’exclure des analyses de target d’approbation ou la traiter séparément, sans effacer son flag du dataset source nettoyé.
8. Journaliser les volumes avant et après chaque étape ainsi que les exclusions par motif. Ajouter des contrôles sur les dates, identifiants, doublons, bornes et cohérence des colonnes ; les écarts connus doivent être signalés et justifiés, pas transformés silencieusement.

## Contraintes temporelles

- Pour toute feature jointe à une votation de date `t`, n’utiliser que l’information qui aurait été publiée et disponible avant `t`. L’année de référence seule ne prouve pas la disponibilité ex ante.
- Privilégier une jointure « as-of » sur la date de publication connue. Si elle n’est pas archivée, adopter une règle conservatrice explicite, documenter l’approximation et conserver le millésime/version utilisé.
- Les historiques de résultats utilisés comme features doivent être strictement antérieurs à la votation cible. Ne pas utiliser un autre objet tenu le même jour comme historique disponible.

## Géographie communale

- Le cube des votations harmonise les résultats à l’état communal du **01.01.2026**. Cet état (`municipality_id`) est la géographie de référence du dataset de votes, y compris pour les résultats historiques ; les frontières historiques ne sont pas nécessairement disponibles dans le cube.
- Avant une jointure de caractéristiques communales, vérifier l’état géographique déclaré par la source et le comparer à son référentiel communal. Ramener ensuite les données à la géographie de référence des votes à l’aide d’une correspondance OFS documentée. L’égalité des codes ne garantit pas à elle seule l’égalité des territoires.
- Pour une fusion ou une urne commune, agréger les grandeurs additives avant la jointure. Recalculer ensuite les taux et pourcentages à partir des composantes agrégées ; ne pas moyenner directement des ratios.
- Signaler et traiter explicitement les unités spéciales, communes sans résultat propre, changements de numéro et transferts partiels de territoire. Ne pas supposer qu’une valeur absente indique zéro.
- Si des agrégats cantonaux sont nécessaires, les calculer à partir des lignes communales de même géographie. Ne pas mélanger ces lignes avec les totaux cantonaux OFS, qui peuvent refléter un autre état géographique.

## Documents de référence

Consulter les détails à jour plutôt que de recopier leurs résultats chiffrés dans cette skill :

- `docs/DATA_VOTES.md` — source OFS, schéma, provenance, particularités et contrôles du dataset de votes ;
- `docs/communal_features_audit.md` — sources candidates de caractéristiques communales et disponibilité temporelle ;
- `docs/geography_compatibility_audit.md` — compatibilité des référentiels communaux et règle de normalisation géographique ;
- `docs/SWISS_VOTING_FEASIBILITY.md` — résultats et périmètre de l’essai de faisabilité, à distinguer du périmètre initial 2013–2024.

Critère de sortie : données reproductibles, provenance conservée, exclusions explicables, contrôles exécutés ou exceptions justifiées, et jointures temporelles et géographiques documentées.
