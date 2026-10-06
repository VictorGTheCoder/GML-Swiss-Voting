---
name: gml-deliverable-check
description: Contrôler l’alignement méthodologique, la reproductibilité et le socle fonctionnel avant une PR importante ou un rendu GML.
---

# Contrôle de livrable GML

À utiliser avant une grosse PR, une fin d’itération, une release ou un rendu intermédiaire/final.

Produire un verdict `READY` ou `NOT READY` et lister les bloqueurs. Vérifier brièvement :

- contribution identifiable au Must ou au Wish du cahier des charges ;
- commande ou procédure de reproduction, provenance des données et versions conservées ;
- tests pertinents présents et exécutables ;
- splits temporels, disponibilité ex ante et absence de fuite vérifiés ;
- expériences, baselines, métriques et choix documentés ;
- cohérence entre code, résultats affichés, artefacts et rapport ;
- application et parcours principal fonctionnels lorsqu’ils sont dans le périmètre ;
- absence de dépendance inutile à un service payant ;
- socle minimal utilisable maintenu avant les extensions.

Ne pas transformer ce contrôle en nouvelle analyse ML : renvoyer les anomalies aux skills
spécialisées. Un point non vérifiable est un bloqueur à documenter, pas une hypothèse silencieuse.
