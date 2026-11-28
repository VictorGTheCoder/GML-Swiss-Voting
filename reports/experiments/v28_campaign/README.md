# V28 — Audit des signaux nationaux ex ante

Suite [V27](../v27_campaign/README.md). V24.1 6,950427808889042 pp; V8.1 gelée 7,229527497606818; V9 7,131910681945383. 66 objets / 23 dates / 138868 lignes de développement. Aucun test final.

## V28.1 — planifié, non exécuté

Hypothèse : les lacunes et la fraîcheur des signaux nationaux expliquent une partie de l'erreur nationale. V10.1/2 ont déjà testé l'ajout brut d'attentes et médias; V11.6 le refit à 23 dates; ne pas répéter ces fits. Vérifier les artefacts V8.1, V10.1/2 et V24.1, leurs empreintes, clés, provenance et dates, séparer intention, part de oui attendue et probabilité d'acceptation. Comparer l'erreur nationale par disponibilité et fraîcheur (0–14, 15–30, >30 jours, absent; publication strictement avant scrutin), sur mêmes clés avec effectifs et incertitude appariée par date. Diagnostic descriptif, pas de fit ni sélection. Ne pas inventer de date. Aucune donnée individuelle ni ciblage; pas de cibles 2023+.

V28.2 : acquisition ciblée de sources contemporaines indépendantes uniquement si lacunes certifiables; licence, identité, date et hash, puis ablation appariée chronologique. Si bloqué, consigner et passer à autre hypothèse. SECO suspendu. Aucun résultat nouveau revendiqué; aucune promotion.

## V28.1 — inventaire des sources mesuré (28 novembre)

Sur 66 clés du catalogue historique : 96 lignes SRG directes (48 objets), 17 paires supplémentaires, 65 objets avec date de publication déclarée; 16/96 graphiques SRG signalés modifiés au jour du vote ou après, 0/96 millésimes strictement vérifiés. Les 37 lignes de part de oui attendue correspondent exactement aux clés objet/date/vague/URL des intentions SRG; elles couvrent 20 objets (18 à 1–14 jours, 2 à >30 jours). Médias : 54 objets (26 à 1–14 jours, 26 à 15–30 jours, 2 à >30 jours), 12 absents. Tamedia : 21 objets avec une publication candidate datée à 1–14 jours; 45 sans candidate dans V13.2, distinct du récapitulatif rétrospectif à 66 objets. Date déclarée ≠ millésime certifié. [Inventaire et empreintes Git](V28.1-source-inventory.json).

Les deux observations médiatiques anciennes du 4 mars 2018 proviennent bien du rapport du 21 décembre 2017 (73 jours avant le vote). Un second rapport fög du 15 février 2018 (17 jours avant), fenêtre 30 octobre 2017–4 février 2018, est retrouvé via APS : [PDF](https://anneepolitique.swiss/references/273398/download?filename=F%C3%B6g-Abstimmungsmonitor_175.3_20180304.pdf&inline=true&locale=fr), [corroboration SRF du même jour](https://medien.srf.ch/-/stellungnahme-von-srf-zur-fog-studie-1). Extraction textuelle page 3 : 1049 articles, tonalité -33 (No Billag) ; 47, +53 (Finanzordnung). Capture PDF en échec (timeout), empreinte et licence à confirmer. Deux candidats seulement, en quarantaine; aucun changement de la source V10.

Audit automatisé V28.1 implémenté : lecture de l'artefact figé V24.1 (run 46060624437, artifact 15228766542), contrôle des 66 objets/23 dates et scores, jointures exactes, dates strictes, agrégats macro-objet par disponibilité et fraîcheur, IC bootstrap apparié par date du gain national V24.1 vs référence dans chaque groupe. Les strates décrivent les données existantes, pas un effet causal du signal; dates réutilisées, pas de nouveau fit ou sélection. Quatre tests ciblés prévus; CI et résultats à vérifier. V24.1 reste à 6,950427808889042 pp. V27.1 relancé automatiquement sur le commit documentaire précédent (run 46133042461, succès); passage en manuel pour éviter répétition.

## V28.1 r1 — échec de périmètre et correction (28 novembre)

[Run initial](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/46138204208) : 4/4 tests ciblés réussis, artefact V24.1 téléchargé avec digest SHA-256 vérifié par GitHub (93b6c94bbb7605e9a1f431540a04d4cfa0644a020831915aab8e93cb152002d7), puis arrêt sur `Source key/date outside pinned population`. [CI générale réussie](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/46138204221). Le fichier SRG direct est mixte : 96 lignes/48 objets au total, dont seulement 48 lignes/24 objets sur 2016–2022; les 48 autres lignes appartiennent à 2023+. Les 17 paires historiques ajoutent 17 objets distincts, soit **41/66** et non 65/66. Les 16 mises à jour tardives concernent les 48 lignes historiques; 0/48 millésimes directs certifiés. Autres couvertures inchangées (20 attentes, 54 médias, 21 candidats Tamedia). Vérification par clés du catalogue historique, à confirmer par jointure à l'artefact figé.

Correctif : projection des colonnes de métadonnées uniquement pour toutes les sources (aucune part de vote en entrée de cet audit), exclusion explicite et comptée des dates SRG 2023+, conservation du refus de toute clé/date historique inconnue, dates manquantes rejetées. Trois tests de régression ajoutés. Le manifeste d'audit exposera le nombre de lignes exclues et la couverture SRG effective. Aucun changement de données source, de modèle ni des fenêtres de référence. Aucun fit; scores par strates non encore mesurés, prochain run à vérifier.


## V28.1 r1 — audit terminé (28 novembre 2026)

[Run](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/46142663637) · [Artefact](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/46142663637/artifacts/15261997019) · [CI](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/46142663630) · [Manifeste exact](V28.1-results.json). 7/7 tests, CI 3/3; 66 objets / 23 dates, scores de référence et meilleur exploratoire contrôlés. Les 48 lignes SRG hors période sont exclues. 41 objets avec date SRG déclarée, 0/48 lignes directes historiques certifiées; 16 mises à jour tardives. Aucun nouvel entraînement.

| Signal | Strate | Objets | Dates | MAE nationale | MAE centrée | MAE communale |
|---|---|---:|---:|---:|---:|---:|
| srg_declared | 0-14 | 41 | 13 | 4.1427 | 4.8245 | 6.7759 |
| srg_declared | absent_or_undated | 25 | 11 | 3.1651 | 6.0514 | 7.2366 |
| expectation_declared | 0-14 | 18 | 7 | 3.1902 | 4.9238 | 6.4600 |
| expectation_declared | >30 | 2 | 2 | 0.7967 | 5.2739 | 5.2770 |
| expectation_declared | absent_or_undated | 46 | 20 | 4.1296 | 5.4329 | 7.2151 |
| media_declared | 0-14 | 26 | 7 | 3.5607 | 4.8366 | 6.3606 |
| media_declared | 15-30 | 26 | 11 | 3.6778 | 5.6249 | 7.2709 |
| media_declared | >30 | 2 | 1 | 3.7247 | 3.3812 | 5.6372 |
| media_declared | absent_or_undated | 12 | 4 | 4.4438 | 5.8607 | 7.7529 |
| tamedia_candidate | 0-14 | 21 | 9 | 3.6984 | 4.7683 | 6.5363 |
| tamedia_candidate | absent_or_undated | 45 | 14 | 3.8069 | 5.5324 | 7.1437 |

La couverture SRG datée ne correspond pas à une erreur nationale plus faible (4,1427 vs 3,1651 pp). Les attentes récentes (3,1902 vs 4,1296) et médias récents (3,5607 vs 4,4438) présentent des écarts descriptifs, mais les objets et dates diffèrent; les strates ne démontrent ni causalité ni effet d'acquisition. Les 2 objets attentes >30 jours sont insuffisants; un seul bloc date pour médias >30 jours. Les IC appariés par date du gain national V24.1 vs référence par strate sont dans le JSON, pas des IC d'effet de disponibilité. La MAE centrée reste importante; se limiter à la correction nationale ne suffit pas. Pas de sélection de modèle sur cet audit. V24.1 reste le minimum exploratoire 6,950427808889042 pp, sur dates réutilisées.

## V28.2a — provenance fög (en quarantaine)

[Source officielle et contrôle](V28.2a-source-audit.json). Les pages 1 et 3 de l'édition UZH du 15 février 2018 ont été vérifiées visuellement; les deux valeurs du miroir APS concordent, 1049/-33 et 47/+53. Fenêtre close le 4 février, 17 jours avant scrutin pour la publication. Ce n'est pas une augmentation de couverture. La tentative de téléchargement local a échoué (DNS, curl 6); pas de hash inventé. Mention © fög / Universität Zürich, aucune licence ouverte spécifique vérifiée; pas de redistribution du PDF ni admission. Suspendre cette acquisition isolée.

## V28.3 — prochain audit préspécifié

Identifier les sources d'ancrage réellement consommées par la référence et V24.1 plutôt que de confondre présence d'une source candidate et utilisation effective; rapprocher leurs identifiants exacts des preuves de publication, des versions rétrospectives et des millésimes certifiés. Si faisable, définir avant tout score une ablation de provenance avec fallback, sur mêmes clés et dates, sans fit sur la date cible. Pas de cibles 2023+, ni de promotion. Si la provenance effective est indéterminable, consigner les limites puis ouvrir une piste indépendante.


## V28.3a — provenance effective (28 novembre 2026)

Inspection du code au commit `fafec841fd49e9251647f04273986e0b5923d5dd` : `robust_v241.run` appelle `contexts`, puis `enrichment_v1089.anchor`. L'ancrage national utilise exclusivement `f.v8_reference` lorsque `poll_available` (sinon le profil structurel propre à V24.1); les marges de langue et d'habitat sont appliquées par `joint_adjust`. La référence V8.1 reproduite dans `expectations_v101` part elle aussi de `f.v8_reference` et des marges. `national_fusion_v81` conserve explicitement la prédiction originale `p` dans cette colonne : les variantes LeeWas/Tamedia et les 17 paires SRG complémentaires n'en sont pas les sources. Les attentes et médias V10 ne sont pas des entrées de cet ancrage.

[Comptage reproductible des fichiers versionnés](V28.3-static-audit.json), réalisé via lecture des CSV au commit parent : **48 objets sur 66** ont deux vagues originales disponibles dans l'assemblage national V3/V5 (24 directs, 24 articles historiques V3, ensembles disjoints; 96 lignes historiques, 0 certifiée). V28.1 recensait 41 objets sur un autre ensemble (24 directs + 17 paires V8.1 complémentaires) : ce n'était pas la couverture effective. Sur les 48 lignes directes historiques, 16 mises à jour tardives et 7 dernières vagues affectées. Le fichier linguistique possède 135 cellules sur 24 objets, 45 mises à jour tardives, 6 objets dont la dernière vague est tardivement modifiée, aucune cellule certifiée. Ces indicateurs ne prouvent pas de modification numérique. Les dates de modification des articles V3 ne sont pas assimilées aux dates de graphique.

L'audit automatisé V28.3a projette seulement les métadonnées de la population figée et des sources nationales, linguistiques et d'habitat; contrôle exact clés, dates, cutoff UTC du code existant, vagues, empreinte du fichier d'habitat, et compte les sources effectivement sélectionnées. Quatre tests synthétiques implémentés; CI et exécution complète à vérifier. Pas de nouveau fit, ni score, ni admission. La couverture exacte d'habitat reste à mesurer sur l'artefact d'acquisition. CI parent 3/3 réussie (46147264175), réexécution V28.1 46147264177 réussie; workflow V28.1 passé en manuel.

**V28.3b préspécifiée**, après contrôle des artefacts : reproduction de V24.1 à configuration identique, puis ablation de toutes les marges non certifiées et de l'ancrage national non certifié (fallback structurel du même modèle, pas une nouvelle source). Comparer les quatre métriques et IC apparié sur 66 objets; vérifier que la reproduction rejoint les prédictions figées. Une ablation « graphiques tardifs seulement » peut servir de sensibilité distincte, jamais de certification des autres. V16.3 testait le niveau structurel du modèle rolling institution, non cette exclusion simultanée des trois signaux du candidat V24.1. Éviter une répétition de blends. L'ablation ne certifie pas les autres familles de features et ne démontre pas une fuite. Aucun accès 2023+, aucune promotion, dates réutilisées.
