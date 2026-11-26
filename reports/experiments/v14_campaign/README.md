# V14 — registre et backlog initial

Suite de [V13](../v13_campaign/README.md), [V11](../v11_campaign/README.md) et [V10](../v10_campaign/README.md). Population inchangée : 66 objets, 23 dates, 138868 lignes de développement, 2016–2022. Meilleur exploratoire V11.3 6,955753873756506 pp. Aucun test final autorisé.

## V14.1 — faisabilité documentaire (ouverte le 25 novembre 2026)

V13.5 : oracle cantonal 3,7517 pp, gain diagnostique 1,4729 pp au-delà de la translation nationale. Aucune preuve que les offsets soient prévisibles. L'inventaire de l'arbre Git au commit aea65e15f4897b5ef34b9eba4d1e250c92665253 confirme un manifeste STATENT V9 déjà présent : ne pas réacquérir ce bloc par défaut. [FAQ OFS STATENT](https://statistik.admin.ch/fr/comprendre-donnees-statistiques/enquetes/statent) : disponibilité à 20 mois du mois de référence et rupture EPT 2014–2015 ; à documenter lors d'un éventuel réaudit, ne pas confondre année de référence et disponibilité.

Piste indépendante : [archives annuelles AFF de péréquation financière](https://www.efv.admin.ch/en/data-fiscal-equalization), jeux annuels depuis 2008, millésimes archivés en ZIP. [Méthodes et rapports](https://www.efv.admin.ch/fr/documents-techniques-et-rapports). Le portail indique des dates de remise en ligne en 2025, non des dates originales ; les montants peuvent avoir été corrigés. **Aucune valeur admise**. Différent des revenus fiscaux communaux V10.9, mais redondance empirique et présence éventuelle de variables équivalentes à contrôler. Hypothèse d'audit : identifier des données publiques institutionnelles agrégées réellement disponibles avant chaque date de développement et documenter la couverture et les révisions. Pas de segmentation électorale ni d'usage politique opérationnel.

| Priorité | Étape | État / garde-fou |
|---|---|---|
| 1 | V14.1 inventaire des publications et versions originales AFF (2008–2022 uniquement), licence, schéma, hash et chevauchement avec blocs existants | Sources candidates identifiées ; télécharger uniquement fichiers admissibles, distinguer consultation et valeurs définitives, ne pas extrapoler la date de publication |
| 2 | V14.2 audit de couverture et redondance des nouvelles données agrégées, sans observations du scrutin cible | Bloqué par V14.1, jointures exactes et contrôles chronologiques |
| 3 | V13.2 certifier sources multi-vagues historiques | 39 observations candidates, 14 objets/5 dates, zéro admission |
| 4 | V13.1/V12.2 récupérer preuves contemporaines des archives | Différé jusqu'à nouvelle preuve |

Pas de résultats prédictifs nouveaux. Pas de répétition automatique des benchmarks terminés. Toute comparaison ultérieure doit préserver la population, le gel V8.1, les fenêtres temporelles et le bootstrap apparié par date ; aucun résultat cible 2023+.

## V14.1a — audit de versions des indices de ressources (26 novembre 2026)

Les six rapports de consultation AFF 2017–2022 sont retrouvés sur le [portail allemand](https://www.efv.admin.ch/de/zahlen-tabellen-berichte-finanzausgleich). Couvertures et tableaux vérifiés visuellement : les documents portent juin de l'année précédente, mais les dates de remise en ligne sont postérieures. Les rapports 2017 (§1.5) indiquent que les tableaux sont remplacés après consultation. L'année 2016 reste à couvrir avec un document disponible avant le premier scrutin, sans récupérer rétroactivement la colonne 2016 du rapport de juin 2016. Les valeurs de l'année courante sont des indices de ressources, base suisse 100, et non des résultats de vote.

Le [CSV candidat](../../../data/external/fiscal_equalization_v141/resource_index_candidates.csv) contient 156 couples canton-millésime distincts, transcrits depuis les tableaux 7 (2017, 2018, 2020–2022) et 8 (2019). Pages PDF numérotées à partir de 1, mois indiqué sur la couverture. Les colonnes de comparaison sont issues du rapport de consultation de l'année suivante et sont **strictement diagnostiques**, jamais des variables prédictives. La comparaison n'établit pas à elle seule la date ni la nature définitive de la révision.

| Millésime | Couples | Comparables au rapport suivant | Indices différents | Écart max (points d'indice) |
|---|---:|---:|---:|---:|
| 2017 | 26 | 26 | 0 | 0.0 |
| 2018 | 26 | 26 | 10 | 0.2 |
| 2019 | 26 | 26 | 0 | 0.0 |
| 2020 | 26 | 26 | 0 | 0.0 |
| 2021 | 26 | 26 | 22 | 0.4 |
| 2022 | 26 | 0 | — | — |

Total : 32/130 indices comparables différents (à la précision publiée). Vérification programmatique indépendante de la cardinalité, de l'unicité et des valeurs positives; aucune jointure au modèle. Le changement de régime 2020 exige une vérification de la comparabilité. Le rapport 2017 précise la fenêtre fiscale de trois ans 2011–2013; ne pas confondre ces années avec la disponibilité. Les droits de redistribution du document complet ne sont pas établis : seules des données factuelles et les références sont conservées, aucun PDF reproduit. Licence spécifique et SHA-256 des fichiers sources à vérifier, ainsi qu'une preuve de publication originale pour chaque millésime. Les valeurs transcrites restent en quarantaine, aucune admission. Pour la suite : récupérer des fichiers originaux ou preuves contemporaines, vérifier 2016, extraire et comparer les autres familles (charges géographiques et sociodémographiques), contrôler la redondance avec les covariables existantes. V14.2 reste bloquée. CI précédente [45717992954](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45717992954) : 3/3 réussis. Aucun benchmark déclenché volontairement sur données non admises; meilleur score V11.3 inchangé.

## V14.1b — couverture 2016 et preuves de publication (26 novembre 2026)

Les 26 indices 2016 du tableau 7 du rapport de juin 2015 ont été retrouvés dans le texte indexé de l'ancienne URL AFF. Le PDF original renvoie 404 lors du rendu : page PDF non confirmée, hash absent. Les 26 valeurs coïncident exactement avec la colonne de comparaison 2016 du rapport 2017, tableau 7, page PDF 23, contrôlée visuellement. Cette seconde source n'est **pas** une source ex ante pour les scrutins du début 2016. Elle reste réservée au diagnostic. Le [communiqué fédéral du 4 novembre 2015](https://www.newsd.admin.ch/newsd/message/attachments/41560.pdf) confirme l'existence de la consultation du 7 juillet 2015 et l'absence de changement des paiements, non l'identité binaire du tableau indexé.

Le [registre des preuves de publication](../../../data/external/fiscal_equalization_v141/publication_evidence.csv) couvre les sept millésimes : deux preuves institutionnelles (2016 et 2017), cinq articles de presse contemporains attestant des annonces ou décisions, mais pas tous de la version exacte du tableau. Pour 2017, le rapport du CDF du 17 octobre 2016, p.21, atteste explicitement la publication conjointe des données et du rapport de consultation fin juin 2016. Les dates du registre sont des dates de preuve, pas des dates de disponibilité certifiées de chaque observation ; ne pas les utiliser directement dans un pipeline prédictif.

Contrôles exécutés sur le CSV complet : 182 clés uniques (7 × 26), 11 champs par ligne, valeurs positives et finies, 156 comparaisons, 32 différences (20,5 %), maximum 0,4 point d'indice. 2016 : 0/26 différence. Tous les statuts restent candidate_not_admitted. Aucun résultat de scrutin utilisé. La CI du commit précédent [45725267596](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45725267596) est passée (3/3 jobs).

**Backlog** : récupérer l'archive ZIP 2016 du portail AFF et vérifier le document original ou une publication contemporaine du tableau exact ; vérifier hashes et conditions de réutilisation sur l'ensemble des sept millésimes ; compléter les indicateurs de charges ; V14.2 reste bloquée pour toute jointure au modèle tant que les données ne sont pas admises. Aucun benchmark déclenché, meilleur score V11.3 inchangé. Aucun accès au test final.
