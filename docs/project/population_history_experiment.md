# Extension historique avec population totale et étrangère

Protocole fixé le 1er novembre 2026 avant les nouveaux entraînements.
L'expérience reste rétrospective, séparée du snapshot de démonstration et de la V1.

## Sources et préparation

Reprendre les stocks de fin d'année OFS du bilan démographique pour 1981–2009,
Total/Étranger, sexe Total. Conserver STATPOP dès 2010, sans substituer le bilan
ESPOP 2010 au stock STATPOP 2010. Les extractions officielles complètes sont
archivées avec requêtes et empreintes ; les CSV RTS restent hors de cette préparation.
Réutiliser les mutations et snapshots du prototype ESPOP contrôlé pour raccorder
les territoires 2025 vers 2026. Ne pas répartir une scission sans preuve. Sommer
les effectifs des constituants d'une fusion avant de calculer les parts.

Écarter les stocks invalides/non positifs et les correspondances non résolues,
en conservant les motifs et la couverture. Une absence ne devient pas un zéro.
Les années non admissibles ne sont pas remplacées par une année future.

Disponibilité : appliquer la même hypothèse rétrospective de sélection que pour
STATPOP, le 2 septembre Y+1, pour choisir le stock annuel avant le vote. Il ne
s'agit pas d'une preuve de publication ESPOP ou STATPOP historique. L'année 1981
est demandée pour les stocks ; les premières lignes de vote avec population
sélectionnable pourront commencer après 1981. La première date effective doit
être mesurée et publiée, sans inventer une valeur en 1980.

## Comparaison prévue

Validation commune : 2021–2022, mêmes clés et mêmes sources pour tous les
candidats ; cette validation a déjà été exposée. Entraînement récent 2012–2020
contre entraînement depuis la première date exploitable jusqu'à fin 2020.
Aucun résultat après 2022 n'est chargé. Les résultats des scrutins de validation
n'entrent pas dans l'historique, gelé à fin 2020. Les historiques des lignes
d'entraînement ne contiennent que des dates strictement antérieures, y compris
les scrutins antérieurs à 1981. Cette politique reste identique dans les deux
régimes : l'expérience mesure l'ajout de lignes d'entraînement, pas un changement
implicite d'historique.

Trois configurations par modèle : historique seul ; historique + typologies +
caractéristiques d'objet ; puis les mêmes variables + population totale et part
étrangère. Ridge alpha = 1 et HistGradientBoosting aux paramètres fixes de la
démonstration. Aucune recherche d'hyperparamètres. Les âges, parts de partis,
recommandations et texte sont exclus de cette comparaison pour ne pas fabriquer
une couverture historique inexistante. Les six configurations sont ajustées dans
les deux régimes, soit douze modèles. Prétraitement réajusté exclusivement sur
chaque train ; mêmes clés de validation pour tous ; prédictions bornées à [0, 1].

Le contraste long − récent à variables identiques isole la profondeur
historique dans ce protocole. Le contraste avec − sans population mesure l'apport
du bloc démographique dans chacun des régimes. Une même population de lignes
avec stock valide est utilisée aussi pour les variantes sans population, pour
ne pas confondre gain de feature et changement d'échantillon.

Comparer MAE communale, moyennes par objet/date et deltas appariés. Conserver
les échecs et la couverture par année. Ne pas comparer directement un modèle
sans âge/partis au score publié du Ridge complet comme si seul l'historique avait
changé. Les observations communales ne sont pas des scrutins indépendants ;
aucun effet causal ni évaluation finale indépendante n'est revendiqué.

## Reproduction et sorties

```bash
python -m scripts.espop.population_history
python -m scripts.modeling.population_history_experiment
```

La première commande réutilise un téléchargement complet vérifié s'il existe ;
sinon elle collecte le bilan officiel, puis prépare les stocks dans
`data/interim/population_history/`. La seconde construit une table distincte,
limitée aux résultats jusqu'à 2022, et écrit dans
`reports/generated/population_history_experiment/` les métriques, prédictions,
contrastes, figures, couverture et manifeste. Les nouvelles tables restent
locales. Les scripts ne modifient pas les données préparées de la démonstration.
