# Sélection et importance des variables pour les votations communales

Recherche méthodologique du 1er novembre 2026. Sources primaires consultées le
même jour. Ce rapport ne modifie aucun modèle, ne sélectionne aucune variable
sur les données et n'ouvre pas le test réservé.

## Recommandation pour ce projet

**Privilégier les comparaisons supervisées par blocs, avec réentraînement et
validation chronologique.** Compléter les ajouts déjà mesurés par des retraits
du modèle combiné ; utiliser ensuite une permutation groupée dont l'unité
respecte les objets et les communes. Réserver PCA, corrélations et variance au
diagnostic de structure et à des variantes de compression à comparer. SHAP
pourrait expliquer certaines prédictions, mais ne remplacerait pas ces
comparaisons de performance.

Il faut distinguer trois questions :

| Question | Outils proposés | Conclusion autorisée |
| --- | --- | --- |
| Quelles variables se ressemblent ou varient peu ? | Corrélations, regroupement, variance, PCA | Structure de `X`, sans pertinence démontrée pour la cible |
| Quelles informations améliorent la prévision ? | Ajouts/retraits réentraînés, permutation sur validation | Utilité prédictive pour un modèle, une population et une période donnés |
| Pourquoi le modèle produit-il cette prédiction ? | Coefficients, éventuellement SHAP | Comportement du modèle ; aucune causalité établie |

Les sections marquées **constat du dépôt** décrivent les fichiers consultés.
Les **recommandations** sont des propositions pour la prochaine expérience.
Une **hypothèse** reste à tester et n'est pas présentée comme un résultat.

## Constat du dépôt : point de départ réel

L'unité est commune × objet fédéral et la cible `oui / (oui + non)`.
Le [README](../../README.md) impose des dates de votation entières dans chaque
partition, des données disponibles au moment de prévoir et des traitements
ajustés sur l'entraînement. La [V1 stricte](../../docs/project/modeling_v1.md)
reste sans population admissible démontrée : les preuves historiques de
publication manquent. Une sélection de variables ne résout pas cette absence.

L'[EDA rétrospective](../datasets/retrospective_demo/structured_eda.md) utilise
83 objets sur 30 dates en entraînement et 24 objets sur sept dates en validation
2021–2022, déjà consultée. Les résultats 2023–2025 restent réservés. À
prétraitement comparable et alpha fixé à 1, l'ajout des métadonnées d'objet à
l'historique complet réduit la MAE de 2,335795 points ; le combiné ne gagne
qu'environ 0,010 point supplémentaire. **Hypothèse :** les métadonnées d'objet
portent l'essentiel du signal complémentaire pour ce Ridge et cette période.
Cela ne démontre pas l'inutilité des autres blocs : aucun retrait du combiné
n'est mesuré dans ce rapport, et les écarts varient fortement selon les objets.

Le [prétraitement Ridge](../../scripts/modeling/regularized_votes.py) impute les
numériques par médiane, les standardise, encode les catégories en one-hot et
ajoute des indicateurs d'absence. Le module
[feature_ablations.py](../../scripts/modeling/feature_ablations.py) compare des
prédictions appariées à `ridge_history` ; sa présence ne signifie pas qu'un
protocole complet de retraits du combiné est exécuté. Le
[protocole EDA](../../docs/project/structured_eda.md) reporte explicitement la
permutation. Les objets ne doivent pas être comptés comme autant d'observations
indépendantes qu'il existe de communes : les caractéristiques d'un objet sont
répétées sur ces communes.

## Comparaison des méthodes

### Variance, corrélations et regroupement : premier diagnostic

`VarianceThreshold` élimine par défaut les variables constantes ; cette
sélection ne consulte pas la cible. Un seuil positif supprime aussi des
variables peu variables, sans mesurer leur apport prédictif.
[Documentation officielle](https://scikit-learn.org/stable/modules/feature_selection.html#removing-features-with-low-variance).

**Recommandation :** signaler les constantes et les colonnes entièrement
manquantes dans chaque entraînement, notamment `party_share_centre` dans le
snapshot EDA. Ne pas éliminer automatiquement les modalités rares ou les
indicateurs d'absence : leur rareté peut être pertinente dans de futurs objets.
Après standardisation, un seuil de variance pour départager les numériques
perd son intérêt ; appliquer ce diagnostic avant la mise à l'échelle.

Le regroupement hiérarchique sur les corrélations de Spearman permet de proposer
des familles redondantes et, éventuellement, un représentant par famille.
C'est notamment la stratégie illustrée par scikit-learn face à la
multicolinéarité.
[Exemple officiel](https://scikit-learn.org/stable/auto_examples/inspection/plot_permutation_importance_multicollinear.html).

**Recommandation :** établir ces groupes sur l'entraînement, en séparant
variables numériques et codes nominaux. Choisir un représentant selon sa
définition, sa couverture et son admissibilité, puis valider son retrait ou son
remplacement. Examiner explicitement les parts d'âge : `80_plus` est inclus
dans `65_plus`, et certaines parts sont compositionnelles. Une forte
corrélation n'est pas une preuve de dispensabilité ; une faible corrélation
par paire n'exclut pas une redondance collective.

### PCA : compression, pas classement de pertinence pour le vote

La PCA crée des combinaisons linéaires orientées vers la variance maximale de
`X`, sans utiliser `y`. L'implémentation scikit-learn centre les colonnes mais
ne les standardise pas. Ses composantes et leur variance expliquée décrivent
la représentation des entrées.
[API PCA](https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.PCA.html).

**Conséquence méthodologique :** un axe expliquant beaucoup de variance n'est
pas nécessairement utile pour la part de oui, et une variable peu représentée
dans les premiers axes peut rester prédictive. Un loading n'est donc pas une
importance prédictive. PCA transforme les variables au lieu de choisir un
sous-ensemble des variables originales.

**Recommandation :** ne pas en faire la méthode principale avec quelques
dizaines de candidats. Si la démographie ou les parts électorales deviennent
beaucoup plus nombreuses, comparer une variante « imputation →
standardisation → PCA du bloc numérique → Ridge » à la variante originale.
Choisir le nombre d'axes par validation temporelle du modèle aval, pas seulement
par un seuil de variance expliquée. Garder catégories, absences et provenance
hors de cette PCA. Le guide officiel distingue également PCA et
`TruncatedSVD`, adapté aux matrices creuses telles que TF-IDF.
[Guide de décomposition](https://scikit-learn.org/stable/modules/decomposition.html).

### Information mutuelle et mRMR : filtres supervisés secondaires

L'information mutuelle avec une cible continue mesure une dépendance, y
compris non linéaire. `mutual_info_regression` exige de distinguer variables
discrètes et continues ; son estimation dépend notamment du nombre de voisins.
[API officielle](https://scikit-learn.org/stable/modules/generated/sklearn.feature_selection.mutual_info_regression.html).

La méthode mRMR combine pertinence vis-à-vis de la cible et faible redondance
entre variables sélectionnées, à l'aide de critères fondés sur l'information
mutuelle. L'article original traite principalement la classification ; son
adaptation à notre régression doit préciser les estimateurs utilisés.
[Peng, Long et Ding, 2005, article original](https://home.penglab.com/papersall/docpdf/2005_TPAMI_FeaSel.pdf).

**Recommandation :** les considérer comme présélection exploratoire si la
dimension augmente, pas comme justification finale d'un retrait. Pour des
métadonnées d'objet, ne pas interpréter la répétition communale comme un grand
échantillon d'objets. Une analyse au niveau objet avec une cible agrégée répond
à une question différente et doit être annoncée comme telle. Mesurer la
stabilité des listes entre fenêtres ; sélectionner `k` dans les seules
fenêtres internes. Un filtre univarié peut manquer une combinaison utile et
ne mesure pas le gain après les historiques déjà présents.

### Régularisation : référence simple et sélection intégrée possible

Ridge utilise une pénalisation L2 ; Lasso peut annuler des coefficients et
Elastic Net combine L1 et L2. En présence de variables corrélées, Lasso peut
retenir un représentant alors qu'Elastic Net tend à conserver le groupe.
[Guide officiel des modèles linéaires](https://scikit-learn.org/stable/modules/linear_model.html).

**Recommandation :** garder Ridge comme référence, puis éventuellement comparer
Elastic Net dans les mêmes fenêtres. Ajuster pénalisation et mélange L1/L2
sans utiliser le test. Ne pas prendre un coefficient nul ou faible comme
preuve d'absence de signal : sa valeur dépend de l'encodage, des autres
variables et de la pénalisation. Dans le dépôt, les coefficients standardisés,
modalités one-hot et indicateurs binaires doivent rester interprétés avec
leurs échelles respectives, comme le prévoit déjà le protocole EDA.

### Ablations réentraînées : priorité proposée

**Recommandation de protocole :** pour chaque fenêtre, comparer l'historique
commun, historique + chaque bloc, combiné, puis combiné − chaque bloc. Le
prétraitement et le modèle sont réajustés après chaque retrait ; remplacer
simplement une colonne par zéro ne constitue pas ce réentraînement.

Définir `Δ_retrait(B) = MAE(combiné sans B) − MAE(combiné)` sur exactement les
mêmes clés. Un delta positif indique un apport conditionnel du bloc dans ce
protocole. L'ajout à l'historique mesure une autre quantité. Deux blocs
redondants peuvent apporter chacun à l'historique mais peu au combiné ; tester
leur retrait conjoint si cette hypothèse motive une simplification.

Une première comparaison à hyperparamètres fixés isole la représentation.
Une seconde, où chaque candidat est réglé dans des fenêtres internes, compare
des procédures optimisées. Rapporter clairement laquelle est réalisée. Garder
couverture, budget de réglage, clipping et pondération identiques.

### Permutation groupée et temporelle : importance du modèle ajusté

La permutation mesure la dégradation du score quand une entrée est mélangée,
sans réentraîner. Elle dépend du modèle et des données évaluées ; des variables
corrélées peuvent se substituer et donner de faibles importances individuelles.
[Documentation officielle](https://scikit-learn.org/stable/modules/permutation_importance.html).

**Proposition spécifique au dépôt, à implémenter et auditer :**

- Pour un bloc d'objet, permuter les vecteurs complets entre objets de la
  fenêtre retenue, puis diffuser chaque vecteur sur toutes les communes de
  l'objet destinataire. Une permutation ligne par ligne détruirait cette
  structure. Une permutation à date identique réduit la rupture temporelle,
  mais devient peu informative avec très peu d'objets par date.
- Pour un bloc communal, permuter des profils communaux complets entre
  communes comparables, en utilisant la même correspondance pour tous les
  objets d'une date. Pour une fenêtre à plusieurs dates, une correspondance
  fixe entre communes préserve davantage la trajectoire du profil, sous
  réserve de géographie compatible. Documenter les strates retenues : elles
  changent la question d'importance.
- Permuter ensemble les variables d'une famille, ses modalités one-hot et
  ses indicateurs d'absence, idéalement avant encodage. Préserver les parts
  liées plutôt que produire des profils incohérents. L'historique dépendant
  de la commune et du cutoff mérite un test séparé, pas une permutation
  arbitraire de ses lignes.
- Ne jamais déplacer une publication future dans une ligne antérieure à son
  admissibilité. Restreindre les échanges aux profils admissibles au cutoff
  destinataire ; si cela empêche une permutation interprétable, rapporter
  « non estimable » et préférer l'ablation.

Ces schémas sont des perturbations de diagnostic, pas une simulation de
communes réelles. Des combinaisons hors distribution restent possibles.
Répéter les tirages avec graines tracées ; rapporter les deltas de MAE en points,
leur dispersion et les résultats par date. La dispersion entre permutations
ne constitue pas l'incertitude de généralisation à de futurs scrutins.

### SHAP : explication complémentaire, après validation

SHAP peut expliquer les sorties d'un modèle ; le traitement des dépendances
entre entrées et le choix du jeu de référence interviennent dans l'explication.
`TreeExplainer` expose notamment des modes différents de perturbation.
[API officielle](https://shap.readthedocs.io/en/latest/generated/shap.TreeExplainer.html).

**Recommandation :** commencer par quelques objets bien et mal prédits ; choisir
un arrière-plan issu de l'entraînement et une agrégation qui ne surpondère pas
les objets ayant davantage de communes. Préciser si l'explication concerne la
sortie brute ou la prédiction bornée. Une moyenne des valeurs absolues décrit
l'amplitude des contributions, pas une baisse de MAE ni une sélection optimale.
Le tutoriel des auteurs montre explicitement qu'une explication prédictive ne
permet pas de déduire l'effet d'une intervention.
[Avertissement causal officiel](https://shap.readthedocs.io/en/latest/example_notebooks/overviews/Be%20careful%20when%20interpreting%20predictive%20models%20in%20search%20of%20causal%20insights.html).

## Prochaine expérience proposée, sans fuite

1. **Choisir le régime.** Une nouvelle analyse sur la démonstration reste
   rétrospective. Pour une revendication de prévision, résoudre d'abord
   disponibilité historique, correspondance des objets et géographie de la
   V1. Geler les prédicteurs autorisés et leur provenance.
2. **Construire des fenêtres chronologiques sur des dates entières.** Les
   communes d'un objet et tous les objets d'une date restent ensemble. Un
   `GroupKFold` sur les seuls objets ne garantit pas l'ordre temporel ; un
   `TimeSeriesSplit` directement sur les lignes peut couper une date. Construire
   les indices à partir des dates puis les diffuser aux lignes. Les méthodes
   de validation groupée et temporelle répondent à des contraintes distinctes.
   [Guide officiel de validation](https://scikit-learn.org/stable/modules/cross_validation.html).
3. **Réajuster tout dans chaque entraînement.** Imputation, encodage,
   corrélations utilisées pour sélectionner, PCA, MI/mRMR et régularisation
   suivent les mêmes frontières. Même un traitement non supervisé peut faire
   fuiter l'information du test. Utiliser une pipeline et réserver les fenêtres
   internes aux choix de sélection.
   [Pièges et prévention officiels](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage).
4. **Mesurer les ablations avant de multiplier les classements.** Comparer
   les mêmes clés commune × objet, avec références historiques identiques,
   mêmes informations connues au cutoff et même politique de réentraînement.
   Publier MAE communale en points, MAE moyenne par objet et par date, ainsi
   qu'une métrique pondérée explicitement distincte si elle est retenue.
5. **Documenter la stabilité.** Rapporter signe et amplitude des gains par
   fenêtre et par date, couverture, fréquence de sélection et sensibilité aux
   groupes corrélés. Le bootstrap par dates déjà présent dans
   [final_evaluation.py](../../scripts/modeling/final_evaluation.py) est
   exploratoire : son propre commentaire signale les limites dues au petit
   nombre de dates et à une éventuelle dépendance sérielle. Sept dates ne
   justifient pas une grande précision.
6. **Geler avant le test.** Liste des variables, transformations, fenêtres,
   réglages, métriques et règles de décision doivent être fixés avant une
   évaluation finale. La validation 2021–2022 ayant déjà guidé l'analyse,
   ses scores restent exploratoires. Une importance observée au test final
   peut servir au rapport ; l'utiliser pour sélectionner de nouvelles
   variables transformerait ce test en validation.

Le livrable expérimental utile serait une table unique par candidat : blocs,
variables, nombre d'objets/dates, couverture, MAE, delta apparié et stabilité
temporelle. **Décision proposée :** retenir une simplification seulement si
son comportement reste acceptable selon un seuil pratique fixé à l'avance,
sans effondrement sur certains objets ou périodes. Aucun seuil ni retrait
définitif n'est déduit ici des scores existants.

L'importance obtenue restera prédictive, conditionnelle au modèle et à cette
population. Les résultats communaux agrégés ne démontrent ni mécanisme causal
ni comportement individuel, conformément au périmètre annoncé dans le README.
