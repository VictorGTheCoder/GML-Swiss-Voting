# Benchmark externe Gradiom — 24 novembre 2026

## Résultat et décision

Sur les 18 objets des sept dates d'archives (24 novembre 2024 au 27 septembre 2026), Gradiom obtient **7.7273 points de MAE communale**, 5.5149 au canton, 4.0229 au national. Les prévisions affichent toutes une date de génération à J-11. Population: 37666 lignes commune-objet, couverture moyenne 99.4088 %. Neuf objets ont des résultats officiels marqués provisoires (mais entièrement dépouillés); les neuf objets définitifs donnent 8.5323 points, les neuf provisoires 6.9222 points. L'intervalle bootstrap descriptif par date (3000 réplications) du score communal est [6.7110, 8.7491]. Ce petit échantillon ne contredit pas nécessairement les performances nationales déclarées sur d'autres périodes.

Sur les sept objets communs à l'ancienne évaluation GML 2023-25, les 14623 lignes sont exactement appariées (2089 communes par objet). Gradiom 8.2755; recette V10.8 gelée, avec repli à l'ancre nationale en l'absence de marges régionales revues, 9.9667. GML est derrière de 1.6912 points, mais seulement trois dates et intervalle descriptif de la différence traversant zéro. Ne pas comparer directement le 6.9886 de la V10.8 en validation 2016-22 avec le 7.7273 de Gradiom en 2024-26. Ne pas promouvoir de modèle à partir de cet échantillon déjà exposé.

## Méthode

- [Plan](../../../experiments/gradiom_benchmark/plan.json). Inventaire de [l'archive Gradiom](https://www.gradiom.ch/en/swiss-popular-votes), pages `/{vote_id}/commune` et `/canton`. Valeurs numériques `data-approval` dans la carte de quantile 50, et national affiché; aucune lecture des couleurs. Vérification des identifiants, dates, niveaux, quantile et date de génération. Les archives actuelles portent des dates antérieures aux scrutins; nous n'avons pas de capture horodatée indépendante prouvant l'immuabilité de chaque page.
- Résultats de l'OFS: `https://ogd-static.voteinfo-app.ch/v1/ogd/sd-t-17-02-{YYYYMMDD}-eidgAbstimmung.json`. Parts calculées à partir des nombres exacts de oui et non. Contrôle du dépouillement complet, exclusion des unités spéciales et résultats sans dénominateur valide.
- Référentiel OFS [communes](https://www.agvchapp.bfs.admin.ch/api/communes), snapshots et mutations avec échanges territoriaux. Cartes 2024-25 en géographie 2024, résultats harmonisés 2026. On exclut les deux côtés de chaque mutation pertinente. En mars 2026 les cartes déclarent `k4voge_20260101_gf` mais contiennent 5 codes hors registre; les codes hors registre et tous les codes mutés sur 2024-26 sont exclus pour ces cartes. Aucun réétiquetage ou interpolation. Les cartes de juin et septembre 2026 correspondent au registre 2026 et tous les 2105 résultats communaux valides sont appariés.
- MAE macro-objet: moyenne simple des erreurs absolues communales en points, puis moyenne simple entre objets. Canton: même méthode, les 26 cantons. National: valeur nationale affichée contre résultat national officiel, non agrégation des communes. MAE centrée: retirer le biais moyen signé au sein de chaque objet puis calculer l'erreur absolue moyenne; diagnostic a posteriori, pas une prévision. 
- Replay GML: 306 objets de 1990-2022 pour l'entraînement; comparaison limitée aux 7 objets communs à la V2 déjà exposés. Aucune optimisation sur les résultats 2023+. Replay V2 exact sur les 18 scores originaux (écart maximal 1.7763568394002505e-15 point); 0 révision de part de oui sur les lignes appariées. L'alignement utilise les sondages publiés au plus tard à 23:59:59 heure suisse le jour de génération affiché de Gradiom; vague 2 disponible à 06:00 sur les trois dates. Heure exacte de génération Gradiom inconnue. Corpus V10.8 historique gelé; 7/7 pages requêtes appariées par les règles existantes. Les paramètres restent ceux du plan de développement. Aucune marge régionale nouvelle non vérifiée, d'où le repli prévu à l'ancre nationale. Le replay est une simulation historique, pas une prévision prospectivement publiée. Les millésimes exacts de publication des sources GML ne sont pas tous certifiés. 

## Gradiom: détails par objet

| Date | OFS | Objet (intitulé archive) | Communes | MAE | MAE centrée | Canton | National | Provisoire |
|---|---|---|---:|---:|---:|---:|---:|---|
| 2024-11-24 | 6730 | Expansion of the motorway network | 2089 | 6.4338 | 6.0104 | 3.6109 | 0.7990 | non |
| 2024-11-24 | 6740 | Conditions for subletting | 2089 | 8.3125 | 5.0132 | 4.8701 | 2.6184 | non |
| 2024-11-24 | 6750 | Termination due to personal need (tenancy law) | 2089 | 11.1603 | 5.2074 | 7.4039 | 4.1695 | non |
| 2024-11-24 | 6760 | Uniform financing of outpatient and inpatient services | 2089 | 7.8433 | 5.5280 | 7.1943 | 5.4108 | non |
| 2025-02-09 | 6770 | «Environmental Responsibility Initiative» | 2089 | 6.2580 | 4.5267 | 3.4204 | 2.1517 | non |
| 2025-09-28 | 6780 | Cantonal taxation of second properties | 2089 | 10.8126 | 7.0916 | 7.8990 | 7.2263 | non |
| 2025-09-28 | 6790 | E-ID Act | 2089 | 7.1082 | 5.4668 | 5.6839 | 4.2138 | non |
| 2025-11-30 | 6800 | Service Citoyen Initiative | 2089 | 10.9741 | 3.4202 | 9.5139 | 9.1456 | non |
| 2025-11-30 | 6810 | «Initiative for a Future» | 2089 | 7.8881 | 3.5422 | 5.8442 | 4.5761 | non |
| 2026-03-08 | 6821 | Initiative «Cash is Freedom» | 2089 | 8.5465 | 8.4306 | 4.7333 | 3.6866 | oui |
| 2026-03-08 | 6822 | Decree on the Swiss currency and cash supply | 2089 | 6.4240 | 5.0498 | 5.7637 | 4.0097 | oui |
| 2026-03-08 | 6830 | Initiative «200 francs is enough!» (fees for public broadcasting) | 2089 | 7.1033 | 6.1070 | 3.4789 | 1.8517 | oui |
| 2026-03-08 | 6840 | Climate Fund Initiative | 2089 | 4.8342 | 4.2942 | 3.0158 | 1.1945 | oui |
| 2026-03-08 | 6850 | Act on Individual Taxation | 2089 | 7.7739 | 5.7976 | 6.9164 | 9.0619 | oui |
| 2026-06-14 | 6860 | «Sustainability initiative» (Limiting the national population) | 2105 | 10.0937 | 8.5029 | 5.8424 | 0.9093 | oui |
| 2026-06-14 | 6870 | Amendment to the Civilian Service Act | 2105 | 7.5459 | 4.5843 | 5.0884 | 3.9585 | oui |
| 2026-09-27 | 6880 | Neutrality Initiative | 2105 | 5.5705 | 5.0735 | 4.7654 | 3.2551 | oui |
| 2026-09-27 | 6890 | «Food Initiative» | 2105 | 4.4078 | 2.6672 | 4.2229 | 4.1731 | oui |

## Comparaison appariée

| Modèle | MAE communale | MAE centrée | Biais signé | Gain vs Gradiom (positif = meilleur) | IC descriptif gain |
|---|---:|---:|---:|---:|---|
| Gradiom publié | 8.2755 | 5.5491 | -3.7317 | 0.0000 | [0.0000, 0.0000] |
| GML V2 original | 10.5232 | 6.2919 | -5.1460 | -2.2476 | [-3.8785, 0.0442] |
| GML V2 aligné | 10.5232 | 6.2919 | -5.1460 | -2.2476 | [-3.8785, 0.0442] |
| GML PCA récente (V7), ancre nationale | 10.2060 | 6.1164 | -5.3363 | -1.9305 | [-3.1599, 1.0784] |
| GML V10.8 TF-IDF, ancre nationale | 9.9667 | 6.1526 | -4.8755 | -1.6912 | [-3.5623, 1.1272] |

| OFS | Objet | Gradiom | V2 | PCA récente | V10.8 |
|---|---|---:|---:|---:|---:|
| 6730 | Expansion of the motorway network | 6.4338 | 7.6482 | 7.4839 | 6.6841 |
| 6740 | Conditions for subletting | 8.3125 | 11.3611 | 10.9082 | 9.3986 |
| 6750 | Termination due to personal need (tenancy law) | 11.1603 | 13.3978 | 13.8560 | 12.8903 |
| 6760 | Uniform financing of outpatient and inpatient services | 7.8433 | 9.3633 | 9.7739 | 10.6181 |
| 6770 | «Environmental Responsibility Initiative» | 6.2580 | 6.2138 | 5.1796 | 5.1307 |
| 6780 | Cantonal taxation of second properties | 10.8126 | 16.7143 | 16.1038 | 17.3374 |
| 6790 | E-ID Act | 7.1082 | 8.9636 | 8.1368 | 7.7081 |

Gradiom gagne 6 objets sur 7 contre V10.8. Le biais absolu moyen par objet est 6.7059 points pour Gradiom et 8.2286 pour V10.8. La MAE centrée reste aussi supérieure pour V10.8 (6.1526 contre 5.5491), donc le défaut ne se réduit pas à l'ancre globale. La fiscalité des résidences secondaires explique 55.1 % du différentiel cumulé sur sept objets; l'hypothèse d'une exposition territoriale mal représentée mérite un diagnostic, mais ne prouve pas quelle variable Gradiom utilise. Les sept objets ne constituent pas un nouveau jeu de validation pour tuner un modèle. La priorité recommandée est un diagnostic de stabilité temporelle / disponibilité historique, puis des caractéristiques d'exposition locale aux mesures avec validation indépendante et ancrage national fiable. Aucun entraînement sur les résultats d'évaluation ni déploiement.

## Reproduction et provenance

- [Inventaire des pages publiques](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45372334039).
- Benchmark 2024-25 [9 objets](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45373347714), [extension 13 objets](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45373726297), [18 objets et six tests réussis](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45374128912). Les deux premières tranches sont reprises par SHA256 dans l'extension finale. 
- [Replay apparié, tests réussis et résultats](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45373542924); artefact corpus [V10.8](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45367633898).
- [Archive de travail du benchmark](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45374128912/artifacts/14909344092): manifest des URL et hashes, audit géographique, scores, lignes appariées (rétention 7 jours). [Artefact comparaison](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45373542924/artifacts/14909752777). Aucun tableau communal propriétaire complet n'est commité.
- Scripts `scripts/modeling/gradiom_benchmark.py`, `scripts/modeling/compare_gradiom_gml.py` et leurs tests. Relancer `python -m scripts.modeling.gradiom_benchmark --output reports/generated/gradiom_fresh` pour une collecte complète dans un répertoire vide; les pages et versions de résultats peuvent évoluer. Le replay requiert les artefacts historiques et la préparation `municipal_v2` telle que définie dans le workflow. Les sorties agrégées vérifiées sont conservées dans ce dossier.
