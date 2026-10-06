---
name: gml-experiment-workflow
description: Encadrer chaque essai de modèle, feature ou transformation pour éviter le tuning opportuniste et conserver les résultats négatifs.
---

# Workflow d’expérience GML

À utiliser lorsqu’un agent veut tester un modèle, une feature, une source ou une transformation,
y compris dans un notebook.

Avant d’exécuter, enregistrer une fiche courte avec :

1. hypothèse falsifiable ;
2. baseline pertinente ;
3. changement expérimental unique ou explicitement groupé ;
4. données, période et features autorisées ;
5. métriques et niveau d’agrégation ;
6. règle de validation et protection du test final.

Puis :

7. exécuter l’expérience avec le protocole temporel du projet, sans regarder ni optimiser le test final ;
8. enregistrer paramètres, version de source/code et résultats, y compris les échecs ;
9. comparer directement à la baseline sur les mêmes observations ;
10. conclure exactement `KEEP`, `REJECT` ou `INCONCLUSIVE`, avec une justification courte.

Une expérience négative est un résultat valide : ne pas supprimer une sortie, changer la métrique
après coup ou ne montrer que les essais favorables. Si plusieurs changements empêchent d’attribuer
le signal, marquer l’essai exploratoire et ne pas le présenter comme une preuve.

Avant `KEEP`, charger aussi les contrôles de fuite de feature et d’évaluation appropriés. Refuser
la multiplication de modèles sophistiqués sans hypothèse, baseline et gain mesurable.
