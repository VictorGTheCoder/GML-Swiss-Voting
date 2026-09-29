# Plan de travail — prédiction des votations cantonales

**Statut :** proposition de cadrage à valider en équipe et avec les enseignants. Le cahier des charges fédéral/communal du 22 septembre 2026 et les scripts OFS présents dans le dépôt documentent l'ancien sujet ; ils ne décrivent pas le pipeline cantonal à réaliser.

## Sujet et résultat attendu

**Question :** dans quelle mesure le titre d'un objet et ses caractéristiques institutionnelles améliorent-ils, au-delà de la moyenne historique du canton, la prédiction de la part de « oui » lors d'une votation cantonale future ?

- **Unité :** objet de votation cantonale dans un canton à une date donnée.
- **Cible :** `oui / (oui + non)`, en points de pourcentage pour l'évaluation.
- **Source principale :** export C2D suisse subnational ; conserver date de collecte, source et règles d'exclusion.
- **Faisabilité provisoire :** audit C2D du 22.09.2026 : 5 891 objets oui/non sur 513 dates distinctes. Kill test Ridge titre + institutions : MAE 11,67 points contre 14,47 pour la référence historique sur le test 2018–2026. Ces chiffres sont exploratoires et doivent être reproduits proprement dans le dépôt.
- **Must :** pipeline reproductible, audit de disponibilité des variables, baseline, modèle Ridge, ablations, validation temporelle sans fuite, MAE/RMSE, application locale montrant une prédiction réelle et ses limites, rapport et défense.
- **Wish, après stabilisation du socle :** intervalle empirique calibré, cas historiques comparables, enrichissement PDF, validation externe sur archive cantonale. La prédiction de participation et l'analyse communale ne font pas partie du cœur du projet.

## Calendrier et exigences du cours

Les documents du cours disponibles indiquent **120 h effectives par étudiant**, un développement par itérations et une **défense annoncée en semaines 14 à 16**. Ils ne fixent pas ici de jour précis de remise, de présentation intermédiaire ou de soutenance. Les échéances calendaires officielles seront ajoutées après communication sur le cours ; ne pas convertir les semaines en dates supposées.

Livrables à suivre dès le début, en plus du code : cahier des charges et organisation (**10 pages recto maximum**), Gantt avec activités/durées/dépendances/jalons/livrables, tableau de répartition des heures, journaux individuels hebdomadaires, modélisation de l'architecture et du pipeline. En fin de projet : application opérationnelle, rapport principal **en un PDF** avec la modélisation finale, sources et ressources déposées selon les consignes Cyberlearn, défense avec participation de chaque membre.

| Étape interne | Période indicative* | Critère de sortie vérifiable |
|---|---|---|
| 1. Cadrage cantonal | Dès maintenant, avant la construction du nouveau dataset | Cahier des charges **réécrit** pour C2D cantonal (Must/Wish et deux itérations), problématique, architecture et schéma de pipeline, rôles avec titulaires/remplaçants, conventions qualité ; Gantt et budget d'heures ; décision sur les scripts communaux existants. |
| 2. Données | Semaines 2–4, à ajuster selon l'avancement réel | Export C2D récupérable ou extrait figé documenté ; version et date enregistrées ; comptage des exclusions, doublons et incohérences ; cantons harmonisés ; cible calculée et contrôlée ; vérification **ex ante** du titre et des métadonnées, avec retrait des variables non défendables. |
| 3. MVP ML | Semaines 4–7 | Référence historique et Ridge entraînés sur les mêmes objets ; séparation chronologique par **dates entières** ; choix effectués sur la validation ; MAE/RMSE globales et par date ; ablations **titre seul / institutions seules / combinaison** ; tests ciblés de fuite. |
| 4. MVP application — objectif intermédiaire interne | Au plus tard vers le milieu du projet | Application Streamlit installable localement ; saisie d'un objet avec variables disponibles avant vote, chargement d'un modèle réel, estimation et métriques principales issues d'une évaluation temporelle ; démonstration sur exemple reproductible. Ce jalon interne ne correspond pas à une remise intermédiaire officielle annoncée. |
| 5. Analyse et amélioration | Semaines 8–10 | Erreurs par canton, type d'objet et période ; analyse des langues et des cas difficiles ; comparaison des modèles structurés si utile ; conclusion nuancée sur la contribution propre du texte. Intervalles et cas similaires uniquement si le socle est stable et que leur méthode peut être vérifiée. |
| 6. Finalisation | Semaines 11–13 ; remise/défense semaines 14–16 selon annonces | Revue croisée d'installation et de résultats, documentation, figures et schémas dans le rapport PDF, journaux et heures à jour, répétition de la démo, dépôt des sources et ressources selon les consignes définitives. |

* Les semaines expriment un ordre de travail indicatif, pas des échéances officielles. L'équipe doit inscrire les dates et responsables dans son Gantt après vérification du calendrier du cours.

### Contrôles méthodologiques non négociables

1. Une date de scrutin reste entièrement dans un seul ensemble ; les transformations sont apprises sur l'entraînement uniquement. Les résultats de l'objet courant, même agrégés, sont exclus des features.
2. Définir train/validation/test et les fenêtres rolling-origin **avant** de consulter le test final. Un kill test antérieur ayant déjà examiné 2018–2026, ne pas traiter ces résultats exploratoires comme une estimation finale entièrement aveugle : documenter cette exposition et, si possible, réserver des dates futures ou une autre vérification indépendante.
3. Auditer si titre et métadonnées C2D existaient avant chaque vote ; mesurer le nombre d'objets pour lesquels l'hypothèse est défendable. Ne pas promettre de prévision prospective avec des variables construites après coup.
4. Distinguer gain sur la moyenne cantonale, gain des institutions et **gain incrémental du texte**. Rapport par objet et par date, car les 5 891 objets ne sont pas indépendants.
5. Un score favorable ne prouve ni causalité ni fiabilité pour une votation isolée. Signaler les exclusions, l'incertitude et les limites dans l'application et le rapport.

## Backlog et séquence immédiate

- Mettre à jour l'issue de cahier des charges [#1](https://github.com/VictorGTheCoder/GML-Swiss-Voting/issues/1) et faire approuver le changement de sujet ; remplacer le document fédéral/communal, sans écraser l'historique de ses travaux.
- Classer [#3](https://github.com/VictorGTheCoder/GML-Swiss-Voting/issues/3) comme **audit terminé de l'ancien périmètre** ; conserver la trace de la PR fusionnée. Fermer [#6](https://github.com/VictorGTheCoder/GML-Swiss-Voting/issues/6) comme abandonnée après pivot, si aucun travail communal n'est encore attendu.
- Adapter [#5](https://github.com/VictorGTheCoder/GML-Swiss-Voting/issues/5) au socle Streamlit puis ouvrir des issues ciblées pour C2D/audit, validation et modèles, intégration de la prédiction, analyse et livraison. Les extensions restent séparées du MVP.
- Les scripts OFS sous `scripts/` et l'audit communal sous `docs/` sont des **artefacts historiques**. Ne pas les présenter comme une implémentation C2D ; décider en équipe s'il faut les archiver ou les déplacer avant de construire le nouveau pipeline.

## Références

- Synthèse des consignes GML et exemples de sujets fournis dans le projet de cours ; vérifier les consignes originales et toute annonce ultérieure.
- Audit ciblé C2D du 22.09.2026 (« GML_Cantonal_Round2 ») : inventaire, protocole des kill tests, limites et risques.
