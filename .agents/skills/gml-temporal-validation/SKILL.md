---
name: gml-temporal-validation
description: Vérifier les splits, historiques, transformations et évaluations qui doivent généraliser vers des votations futures.
---

# Validation temporelle GML

À utiliser pour un split train/validation/test, une CV, un rolling-origin, une feature historique,
un preprocessing dépendant des données, un entraînement ou une évaluation.

Avant de coder ou de modifier le protocole, écrire dans la note de l’expérience :

- l’unité statistique réellement utilisée (pour le périmètre cantonal : objet × canton × date ;
  si le code manipule des lignes communales, le préciser) ;
- l’unité de groupement temporel : au minimum la date de votation ;
- la date à laquelle chaque information est disponible ;
- ce qui est appris sur train uniquement.

Procédure obligatoire :

1. Construire les ensembles chronologiquement. Ne jamais utiliser un split aléatoire ligne par ligne
   pour mesurer la généralisation temporelle.
2. Garder toutes les observations d’une même date dans un seul ensemble. Vérifier automatiquement
   `dates(train)`, `dates(validation)` et `dates(test)` disjoints et ordonnés.
3. Pour une observation à la date `D`, calculer les historiques avec des dates strictement `< D`.
   Les autres objets du même jour sont futurs pour cette observation.
4. Fitter imputation, normalisation, vocabulaire, sélection de features, encodeurs et modèles
   uniquement sur les données autorisées au fold ou à l’origine courante. Refaire ce fit à chaque fold.
5. Geler le test final avant toute sélection de feature, modèle ou hyperparamètre. Le test ne sert
   qu’au bilan final.
6. Si le mécanisme de split ou d’historique change, ajouter ou mettre à jour des tests ciblés,
   notamment absence de chevauchement et stricte antériorité.

Sortie minimale avant de conclure : bornes de dates par ensemble, assertions de non-chevauchement,
preuve de l’antériorité des sources historiques et liste des objets appris sur train. Si une date de
disponibilité ou une fuite ne peut pas être établie, arrêter la conclusion de généralisation et
marquer le point à investiguer.
