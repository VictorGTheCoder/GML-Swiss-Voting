# Campagne V10 — rapport de reprise, 24 novembre 2026

**10/10 étapes mesurées.** Référence V8.1 7,2295 pp ; meilleur score exploratoire V10.8 6,9886000 pp (V10.7 7,1314515 pp ; V9 7,1319107 à ré-auditer). Objectif 4 pp. Les 66 objets / 23 dates / 138 868 observations restent identiques. Les expériences sont comparées séparément à V8.1, sauf mention explicite. Pas de promotion.

[Rapport du matin — toutes les configurations V10.1 à V10.5](morning-report-20261124.md) · [Plan](../../../experiments/municipal_v10/plan.json) · [Journal](README.md)

| Version | Meilleure variante active (extension si disponible) | Commune | Canton | Suisse | Statut |
|---|---|---:|---:|---:|---|
| V8.1 | Référence | 7,2295 | 5,7037 | 3,7757 | Gelée |
| V9 | E5 document 16 | 7,1319 | — | — | Exploratoire |
| V10.1 | expectation25 | 7,2145 | 5,6634 | 3,8082 | Gain non robuste |
| V10.2 | tone_volume | 7,2271 | 5,6743 | 3,8250 | Gain non robuste |
| V10.3 | last_reanchor | 7,2169 | 5,7052 | 3,7757 | Gain non robuste |
| V10.4 | margin_ridge | 7,2039 | 5,6974 | 3,7757 | Gain non robuste |
| V10.5 | centered25 | 7,2441 | 5,7010 | 3,7710 | Dégradation |
| V10.6 | center_shrink25 | 7,2630 | 5,7157 | 3,7459 | Dégradation |
| V10.7 | object_identity | 7,1315 | 5,6408 | 3,7757 | Gain non confirmé |
| V10.8 | page_tfidf_16_all | 6,9886 | 5,5370 | 3,8465 | Gain non confirmé |
| V10.9 | income_means_100 (fiscalité) | 7,2332 | 5,7064 | 3,7746 | Aucun gain |
| V10.10 | adaptive_all_variants | 7,1201 | 5,6053 | 3,8042 | Gain non confirmé |

## V10.6 — toutes les configurations

[Benchmark 45358533701](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45358533701) · [Artefact 14902549065](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45358533701/artifacts/14902549065) · 4 tests ciblés réussis.

| Variante | Commune | Centrée | Canton | Suisse | IC gain |
|---|---:|---:|---:|---:|---|
| reference | 7.2295 | 5.3701 | 5.7037 | 3.7757 | [0.0000, 0.0000] |
| pooled_control | 7.2295 | 5.3701 | 5.7090 | 3.7710 | [0.0000, 0.0000] |
| abs_diag | 7.4561 | 5.3945 | 6.0196 | 4.4476 | [-0.5936, 0.1311] |
| abs_shrink75 | 7.3595 | 5.4198 | 5.8321 | 4.0977 | [-0.4085, 0.1411] |
| abs_shrink25 | 7.3857 | 5.4474 | 5.8646 | 3.9903 | [-0.4451, 0.1101] |
| center_diag | 7.2855 | 5.4249 | 5.7266 | 3.7715 | [-0.1233, 0.0120] |
| center_shrink75 | 7.2681 | 5.4149 | 5.7137 | 3.7462 | [-0.1088, 0.0325] |
| center_shrink25 | 7.2630 | 5.4009 | 5.7157 | 3.7459 | [-0.1627, 0.0938] |
| abs_anchor75 | 7.2952 | 5.4354 | 5.7189 | 3.7710 | [-0.1664, 0.0204] |
| center_anchor75 | 7.2780 | 5.4157 | 5.7242 | 3.7710 | [-0.1129, 0.0164] |

## Analyse

- Aucune des huit réconciliations actives ne bat la référence communale 7,2295. Le meilleur ajustement est `center_shrink25`, 7,2630 (+0,0335 pp d'erreur). Son gain descriptif apparié [−0,1627 ; +0,0938] pp traverse zéro.
- `center_shrink25` réduit l'erreur nationale de 3,7757 à 3,7459 (poids propres) et 3,7398 (poids communs), mais dégrade l'erreur centrée de 5,3701 à 5,4009, et la MAE cantonale de 5,7037 à 5,7157 (poids propres), 5,7054 (poids communs).
- Les ajustements absolus sont moins performants. Cela concorde avec V10.5 : les prévisions cantonales absolues indépendantes atteignaient 9,1564 pp de MAE cantonale, contre 5,70896 pour le bottom-up et 5,9581 pour les contrastes directs recentrés. Une réconciliation ne crée pas à elle seule une source d'information supplémentaire.
- Le nombre d'erreurs hors-échantillon antérieures est faible vis-à-vis des 53 composantes du système. La régularisation est indispensable ; le benchmark ne constitue pas un test de toutes les formes de MinT. Les intervalles sont descriptifs et les dates déjà utilisées pour le développement.
- CI dédiée réussie. Le contrôle général initial a détecté C417 (map/lambda superflu), corrigé par une expression génératrice équivalente avec ce rapport ; résultat du nouveau contrôle à vérifier.

Décision : ne pas promouvoir. Réutiliser l'artefact de prédictions hors-échantillon dans une comparaison d'ensemble chronologique si pertinent, mais ne pas sélectionner les variantes en fonction de l'objet courant. Poursuivre à V10.7. Aucun déploiement, aucun résultat 2023+ dans la modélisation.


## V10.7 — toutes les configurations

# V10.7 — Résultats

[Protocole](V10.7-protocol.md) · [benchmark réussi](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45361300769) · [artefact](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45361300769/artifacts/14904333272). Trois tests ciblés et contrôle général réussis.

| Variante | Commune | Centrée | Canton | Suisse | IC gain |
|---|---:|---:|---:|---:|---|
| reference | 7.2295 | 5.3701 | 5.7037 | 3.7757 | [0.0000, 0.0000] |
| mean_identity | 7.2018 | 5.3309 | 5.6810 | 3.7757 | [-0.0649, 0.1228] |
| object_identity | 7.1315 | 5.2630 | 5.6408 | 3.7757 | [-0.0070, 0.2153] |
| object_latent | 7.1328 | 5.2695 | 5.6397 | 3.7757 | [-0.0150, 0.2214] |
| object_geo | 7.1490 | 5.2864 | 5.6495 | 3.7757 | [-0.0301, 0.2080] |
| object_hybrid | 7.1483 | 5.2897 | 5.6502 | 3.7757 | [-0.0331, 0.2127] |
| object_hybrid_strong | 7.1468 | 5.2783 | 5.6463 | 3.7757 | [-0.0175, 0.1931] |
| object_hybrid_full | 7.2894 | 5.4649 | 5.7585 | 3.7757 | [-0.3020, 0.2102] |

Noyau objet seul : gain de 0,0981 pp par rapport à V8.1, MAE centrée 5,2630 contre 5,3701, canton 5,6408 contre 5,7037. National inchangé. 54 objets corrigés, 12 objets warmup sans correction. Le gain descriptif [-0,0070 ; 0,2153] traverse zéro. Nouveau meilleur score exploratoire 7,1314515, presque égal à V9 7,1319107. Le noyau spatial n'ajoute pas de gain clair ; force intégrale dégrade. Aucun déploiement. Les variantes restent distinctes et utilisables comme candidats prédéfinis dans V10.10.


## V10.8 — toutes les configurations

# V10.8 — Résultats : reconstruction du corpus des brochures

[Protocole commun](V10.8-9-protocol.md) · [Audit](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45366979764) · [Benchmark réussi](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45367633898) · [Acquisition](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45367633898/artifacts/14906199977) · [Prédictions et métriques](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45367633898/artifacts/14907756689). 3 tests ciblés réussis.

| Variante | Commune | Centrée | Canton | Suisse | IC gain |
|---|---:|---:|---:|---:|---|
| reference | 7.2295 | 5.3701 | 5.7037 | 3.7757 | [0.0000, 0.0000] |
| title_e5_16_all | 7.2602 | 5.5482 | 5.6289 | 3.7719 | [-0.2578, 0.2030] |
| title_e5_16_local | 7.3705 | 5.5482 | 5.7506 | 3.7600 | [-0.3180, 0.0322] |
| page_e5_16_all | 7.4125 | 5.4510 | 5.8175 | 3.9644 | [-0.4384, 0.1030] |
| page_e5_16_local | 7.3066 | 5.4510 | 5.7010 | 3.7601 | [-0.2547, 0.1329] |
| page_tfidf_16_all | 6.9886 | 5.2810 | 5.5370 | 3.8465 | [-0.0335, 0.6264] |
| page_tfidf_16_local | 7.1329 | 5.2810 | 5.6003 | 3.8333 | [-0.0179, 0.2398] |
| page_e5_cues_16_all | 7.3586 | 5.4248 | 5.7817 | 3.9554 | [-0.3949, 0.1575] |
| page_e5_cues_16_local | 7.2943 | 5.4248 | 5.6972 | 3.7705 | [-0.2250, 0.1339] |
| cues_only_all | 7.1458 | 5.3455 | 5.6479 | 3.8227 | [-0.0236, 0.1870] |
| cues_only_local | 7.2046 | 5.3455 | 5.6590 | 3.7748 | [-0.0330, 0.0874] |

## Qualité des données et analyse

- L'ancien parseur de sections peut associer le titre de l'objet suivant au corps de l'objet précédent (cas constatés en mars et juin 2021). V9 doit donc être ré-auditée ; son score ne valide pas la qualité des résumés.
- 306 objets avec titre, 217 pages candidates appariées par source/date/hash + titre/question unique, dont 59/66 objets de validation. Les 7 objets non appariés utilisent le titre. E5-small multilingue (révision fd1525a9fd15316a2d503bf26ab031a61d056e98, 384 dimensions) ; TF-IDF et réduction à 16 composantes ajustés uniquement sur l'entraînement. Les indices de mécanismes sont des occurrences lexicales, pas des labels de direction politique validés. Les pages candidates ne garantissent pas une segmentation exhaustive du texte ni une date de publication certifiée. Certaines comprennent du contexte de brochure ou des recommandations et votes parlementaires préalables, distincts des résultats populaires.
- `page_tfidf_16_all` : 6,9886 pp, gain 0,2409 pp (3,33 %) ; centrée 5,2810, canton 5,5370, mais nationale 3,8465 contre 3,7757. IC descriptif [−0,0335 ; 0,6264] pp, traverse zéro. `page_tfidf_16_local` : 7,1329, même MAE centrée, moins bon globalement. E5 page seule n'améliore pas la référence.
- Par fenêtre (référence → TF-IDF all) : 2016–18 (30 objets) 8,1525 → 7,6968 ; 2019–20 (12) 7,1501 → 6,9430 ; 2021–22 (24) 6,1156 → 6,1261. 35 objets améliorés / 31 dégradés, 12 dates améliorées / 23. Gain concentré dans les premières fenêtres, pas de confirmation récente. Sur les 59 appariés : 7,3700 → 7,1383 ; les 7 non appariés restent dans le score.

Décision : meilleur candidat exploratoire, ne pas promouvoir. Corpus à vérifier manuellement (y compris correspondance et date de publication), benchmark indépendant nécessaire. Aucune cible 2023+ dans la modélisation.

## V10.9 — toutes les configurations

# V10.9 — Résultats : revenus et distribution fiscale

[Protocole commun](V10.8-9-protocol.md) · [Audit des sources](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45366979764/artifacts/14906299547) · [Première acquisition](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45367633898/artifacts/14907227679) · [Premier benchmark](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45367633898/artifacts/14908300588) · [Acquisition corrigée](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45368450007/artifacts/14907467639) · [Benchmark corrigé](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45368450007/artifacts/14908660768). Job income réussi, 4 tests ciblés.

| Variante | Commune | Centrée | Canton | Suisse | IC gain |
|---|---:|---:|---:|---:|---|
| reference | 7.2295 | 5.3701 | 5.7037 | 3.7757 | [0.0000, 0.0000] |
| demographic_control_30 | 7.2312 | 5.3729 | 5.6854 | 3.7755 | [-0.0406, 0.0286] |
| demographic_control_100 | 7.2285 | 5.3695 | 5.6896 | 3.7783 | [-0.0227, 0.0199] |
| income_means_30 | 7.2334 | 5.3773 | 5.7061 | 3.7739 | [-0.0094, 0.0018] |
| income_means_100 | 7.2332 | 5.3770 | 5.7064 | 3.7746 | [-0.0087, 0.0015] |
| income_distribution_30 | 7.2391 | 5.3874 | 5.7085 | 3.7728 | [-0.0210, 0.0026] |
| income_distribution_100 | 7.2377 | 5.3860 | 5.7086 | 3.7743 | [-0.0178, 0.0021] |
| income_demographic_30 | 7.2403 | 5.3889 | 5.6921 | 3.7746 | [-0.0541, 0.0249] |
| income_demographic_100 | 7.2369 | 5.3849 | 5.6966 | 3.7781 | [-0.0350, 0.0170] |

## Analyse et traçabilité

- 16 années AFC (2003–2018), géographie historique au 1er janvier de l'année fiscale, contrôlée avec snapshots OFS et mutations jusqu'en 2026. Les 354 noms corrompus en 2012 ont été récupérés par comparaison exacte de la transformation d'encodage avec le nom du même code officiel (pas de correspondance floue). Les 1766 communes cibles initiales de 2012 passent à 2105. Total 33645 lignes (99.66 % du rectangle), 2110 communes cibles. Source et référentiel gelés, empreintes dans manifest.
- Les quatre moyennes ont zéro valeur manquante parmi les lignes retenues. Les trois médiane/Gini ne sont pas agrégés après fusion ; taux manquants 8.29 %. Le délai de publication année +4 est une approximation conservatrice, pas une preuve de disponibilité historique de la version actuelle. Revenus des unités fiscales, pas revenus individuels. Les échanges de territoire ne sont pas demandés au registre, donc limitation du rapprochement.
- Régression ridge des coefficients d'exposition sur les résidus PCA, support d'apprentissage identique 41/71/83 objets par fenêtre (fiscalité seule 69/99/111 disponibles). Toutes les variantes sont évaluées sur 66 objets, pas uniquement les lignes complètes. Les indicateurs de couverture d'objet de la suite income indiquent la population évaluée et non une couverture à 100 % de chaque variable.
- Avant correction, meilleure variante fiscale `income_means_100` 7,2333 ; après correction 7,2332 (IC gain [−0,0087 ; +0,0015]). Démographie seule 7,2285. La récupération de données ne change pas la conclusion : aucune valeur ajoutée fiscale robuste dans ce modèle d'interaction. Les régressions sont peu informées à l'échelle de l'objet ; cela ne démontre pas que les revenus sont sans effet dans la réalité.

Décision : ne pas promouvoir. Conserver acquisition reproductible, tester d'autres interactions sur une validation indépendante. Aucun résultat 2023+ dans la modélisation.

## Scores de la première exécution

| Variante | Commune | Centrée | Canton | Suisse | IC gain |
|---|---:|---:|---:|---:|---|
| reference | 7.2295 | 5.3701 | 5.7037 | 3.7757 | [0.0000, 0.0000] |
| demographic_control_30 | 7.2312 | 5.3729 | 5.6854 | 3.7755 | [-0.0406, 0.0286] |
| demographic_control_100 | 7.2285 | 5.3695 | 5.6896 | 3.7783 | [-0.0227, 0.0199] |
| income_means_30 | 7.2335 | 5.3773 | 5.7061 | 3.7745 | [-0.0094, 0.0016] |
| income_means_100 | 7.2333 | 5.3769 | 5.7064 | 3.7749 | [-0.0087, 0.0013] |
| income_distribution_30 | 7.2389 | 5.3869 | 5.7079 | 3.7736 | [-0.0202, 0.0024] |
| income_distribution_100 | 7.2377 | 5.3857 | 5.7084 | 3.7747 | [-0.0175, 0.0018] |
| income_demographic_30 | 7.2400 | 5.3884 | 5.6918 | 3.7756 | [-0.0534, 0.0248] |
| income_demographic_100 | 7.2369 | 5.3847 | 5.6966 | 3.7787 | [-0.0347, 0.0166] |

## V10.10 — toutes les configurations

# V10.10 — Résultats : ensemble chronologique

[Protocole](V10.10-protocol.md) · [Benchmark réussi](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45368857137) · [Prédictions et métriques](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45368857137/artifacts/14908236884). 3 tests ciblés réussis. Première tentative ensemble (run 45368450007, job 138357552211) échouée à cause du sous-répertoire de V10.1 ; corrigée par détection d'un bundle unique avec manifeste et SHA-256, testé. Le job fiscal de ce run a réussi et son artefact est réutilisé.

| Variante | Commune | Centrée | Canton | Suisse | IC gain |
|---|---:|---:|---:|---:|---|
| reference | 7.2295 | 5.3701 | 5.7037 | 3.7757 | [0.0000, 0.0000] |
| fixed_equal_families | 7.1597 | 5.3225 | 5.6200 | 3.7230 | [0.0180, 0.1209] |
| fixed_half_reference | 7.1907 | 5.3439 | 5.6594 | 3.7352 | [0.0131, 0.0641] |
| adaptive_family_uniform | 7.1686 | 5.3113 | 5.6325 | 3.7481 | [-0.0268, 0.1500] |
| adaptive_family_reference | 7.1876 | 5.3285 | 5.6595 | 3.7571 | [-0.0141, 0.1009] |
| adaptive_family_reference_weak | 7.1699 | 5.3129 | 5.6390 | 3.7644 | [-0.0464, 0.1782] |
| adaptive_all_variants | 7.1201 | 5.3042 | 5.6053 | 3.8042 | [-0.0267, 0.2666] |
| split_level_local | 7.1903 | 5.3196 | 5.6629 | 3.7585 | [-0.0392, 0.1172] |

## Analyse

- 56 candidats (référence unique + 55 variantes actives de neuf familles), aucune sélection du gagnant global de chaque famille. Les poids convexes adaptatifs apprennent uniquement les erreurs OOF de dates antérieures, avec prior et régularisation, pas de même date. Matrice de poids, métriques par objet/fenêtre/canton, corrélations des erreurs moyennes signées par objet et empreintes sources dans l'artefact.
- Meilleur ensemble : `adaptive_all_variants`, 7,1201 (gain 0,1095, IC [−0,0267 ; +0,2666]), canton 5,6053, national 3,8042. Ne dépasse pas le TF-IDF seul. Les poids uniformes par famille donnent 7,1597 (gain 0,0698, IC descriptif [+0,0180 ; +0,1209]), nationale 3,7230, canton 5,6200. L'IC est positif sur ces dates réutilisées mais n'est ni corrigé pour la multiplicité ni une preuve prospective.
- Moyenne uniforme par fenêtre : 8,0724 / 7,0528 / 6,0723 ; adaptation toutes variantes : 8,0309 / 6,8304 / 6,1263. Référence : 8,1525 / 7,1501 / 6,1156. Le gain de la moyenne uniforme est plus régulier mais faible.
- Corrélation des erreurs moyennes signées par objet avec la référence : 0,930 pour V10.1 ; 0,971 V10.5 ; 0,995 médias ; 0,997 GP ; 0,996 texte ; quasi 1 pour fiscalité et participation. Les erreurs agrégées sont très communes ; cela limite la diversification. Ce ne sont pas des corrélations des résidus communaux individuels.
- Au dernier scrutin de validation, poids adaptatif toutes variantes de 34,43 % sur TF-IDF all, 12,47 % sur GP hybride plein, 10,56 % sur canton absolute50. Ils proviennent des 62 objets de dates strictement antérieures, pas de ce scrutin. Ils ne sont pas des recommandations de pondération de production.

Décision : aucun remplacement. Garder le TF-IDF V10.8 comme meilleur candidat exploratoire et l'ensemble fixe comme contrôle de stabilité. Les dates ont été réutilisées pour développer ces méthodes ; l'ensemble est chronologique mais la campagne n'est pas un test final indépendant.

## Conclusion de la campagne

10/10 étapes mesurées. Le score passe de 7,2295 à 6,9886 pp sur les mêmes 66 objets, 23 dates. Gain 0,2409 pp (3,33 %), objectif 4 non atteint (écart 2,9886). La réduction des erreurs locales est modeste ; l'exploration des données historiques reste prioritaire. Meilleures pistes : auditer complètement les brochures et leur disponibilité avant scrutin, comparer représentations lexicales multilingues, noyaux sur objets et corrections locales avec un protocole fixé d'avance ; examiner de nouvelles données réellement informatives plutôt que multiplier les variantes proches. Une validation réellement indépendante et une provenance as-of certifiée restent indispensables. Pas de promotion, pas de modification de main, pas de résultats 2023+ dans les ajustements. Les statistiques fiscales sont conservées avec leurs limites ; les médianes/Gini ne sont pas inventés. La tâche planifiée a été désactivée ; les dernières étapes ont été exécutées interactivement via jobs GitHub Actions, pas par des sous-agents IA.

Contrôle général du commit des benchmarks [45368856959](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45368856959) au moment de la consolidation : tests (windows-latest): success; municipal-experiments: success; tests (ubuntu-latest): success. Les benchmarks dédiés et leurs tests ciblés ont réussi.
