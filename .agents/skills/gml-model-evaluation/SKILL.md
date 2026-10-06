---
name: gml-model-evaluation
description: Évaluer les modèles de part de oui contre des références et vérifier qu’un gain est réel, stable et attribuable.
---

# Évaluation des modèles GML

À utiliser pour un entraînement, une comparaison, l’ajout d’un modèle, une nouvelle métrique ou
la production de résultats expérimentaux.

Avant l’expérience, fixer les mêmes observations, le même split temporel et la même unité de
comparaison pour tous les modèles. Comparer, selon le périmètre disponible :

- baseline historique ;
- modèle structuré simple ;
- texte seul ;
- structuré seul ;
- texte + structuré ;
- modèle candidat plus complexe uniquement s’il répond à une hypothèse et à une baseline.

Rapporter autant que possible, sur les mêmes objets : MAE, RMSE, gain absolu contre la baseline,
gain relatif, dispersion, performance par période, canton et type/famille d’objet pertinente.
Lorsque plusieurs lignes représentent un même scrutin, fournir aussi une agrégation par date ou
par objet afin qu’un scrutin très fourni ne domine pas la conclusion.

Prévoir les ablations nécessaires pour isoler le signal : texte seul, institutions/variables
structurées seules, puis combinaison. Une importance de variables ne remplace pas ces ablations.

Le test final reste gelé pendant la sélection. Un modèle complexe ne peut être présenté comme
meilleur que si le gain est démontré sur la métrique annoncée, stable à l’échelle pertinente et
compatible avec les analyses par sous-groupes. Sinon, conclure explicitement `gain non démontré`
et conserver le résultat, y compris si l’expérience échoue.
