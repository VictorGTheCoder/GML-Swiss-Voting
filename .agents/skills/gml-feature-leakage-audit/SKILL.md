---
name: gml-feature-leakage-audit
description: Auditer la disponibilité ex ante et les dépendances au résultat de chaque nouvelle feature ou source du projet GML.
---

# Audit de fuite des features

À utiliser pour toute nouvelle feature, colonne C2D, source enrichie, agrégat historique,
métadonnée ou document ajouté au modèle.

Pour chaque feature importante, consigner brièvement :

1. source exacte, colonne, version et date de collecte ;
2. signification et unité ;
3. date de référence et moment où la valeur est devenue disponible ;
4. disponibilité avant la votation prédite, idéalement avec une règle as-of ;
5. dépendance directe ou indirecte au résultat, à la participation ou à un agrégat du scrutin cible ;
6. utilisation d’information future, d’une révision ou d’une reconstruction a posteriori ;
7. traitement retenu pour les valeurs sans historique de publication.

Point de garde C2D : la présence actuelle d’une variable dans C2D ne prouve pas qu’elle était
connue avant la votation. Une date de référence historique ne suffit pas non plus si la publication
est postérieure. Les métadonnées, textes ou classifications ajoutés après coup sont présumés
`INVESTIGATE` tant que leur disponibilité ex ante n’est pas documentée.

Décider explicitement :

- `ALLOW` : disponibilité pré-vote et absence de dépendance au résultat établies ;
- `REJECT` : fuite avérée, valeur future ou information indisponible au moment de la prédiction ;
- `INVESTIGATE` : preuve temporelle ou sémantique insuffisante.

Joindre une justification d’une ou deux phrases à la décision. Une feature `INVESTIGATE` ne doit
pas entrer dans le modèle final ni dans le test final ; elle peut seulement rester dans une branche
ou une expérience explicitement marquée. Ne pas remplacer silencieusement une feature rejetée par
sa version courante ou par une imputation qui conserve la fuite.
