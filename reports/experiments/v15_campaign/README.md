# V15.1 — Documents techniques institutionnels (26 novembre 2026)

Suite de [V13](../v13_campaign/README.md) et [V14](../v14_campaign/README.md). V10 : 10/10. V8.1 7,229527497606818 pp; V9 7,131910681945383; V11.3 6,955753873756506 pp, 66 objets/23 dates/138868 lignes. Aucun nouveau score, aucun holdout, aucune promotion. CI parent [45816362190](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45816362190), 3/3 jobs.

## V15.1a — pilote mesuré, sans admission

Hypothèse d'audit : des documents techniques d'offices fédéraux distincts des brochures peuvent apporter un contexte supplémentaire (mécanismes, quantifications, rapports de consultation). Sélection ciblée de sept objets déjà présents dans le développement, trois dates, dont les dossiers liés 614/615 et les lacunes V12. Ne pas extrapoler la couverture à 66 objets. Critères : documentation institutionnelle indiquée neutre au catalogue, date inscrite strictement antérieure (fin du mois pour dates mensuelles), exclusion des corrections de brochures, argumentaires et sources non institutionnelles. Ce n'est pas une garantie de neutralité, de publication historique, ni de droits. Les catégories du catalogue sont rétrospectives : ne jamais utiliser leur nombre, absence, ou classification comme feature sans preuve as-of.

Résultat exécuté :

```json
{
  "sample_objects": 7,
  "sample_dates": 3,
  "candidate_objects": 6,
  "candidate_dates": 3,
  "catalog_entries": 34,
  "object_family_pairs": 17,
  "provisional_distinct_families": 15,
  "month_precision_entries": 10,
  "excluded_catalog_entries": 9,
  "primary_mirror_checks": 2,
  "training_rows_admitted": 0,
  "negative_controls_passed": 6
}
```

Les 34 entrées linguistiques correspondent à 17 couples objet-famille et 15 familles provisoires, pas 34 informations indépendantes. Les dossiers 614/615 partagent deux familles et classent deux autres documents de la même réforme différemment (Ja vs Neutral), donc exclusion des quatre associations ambiguës. Les familles sont regroupées manuellement par intitulé/date, sans prétendre à une identité binaire. 628 : aucun candidat selon cette règle, pas preuve d'absence de documents. Sept pages sources et deux paires miroir/éditeur sont dans le [manifeste](../../../data/external/institutional_v151/catalog_pilot.json).

- OFAS 627 : couverture du 18.02.2019 identique visuellement (page 1) sur le miroir Swissvotes et le site officiel. Le document présente des calculs financiers et scénarios prospectifs; aucun chiffre ni texte intégral exporté. Identité binaire et date de première publication non établies.
- OFSP 656 : couverture du miroir avril 2022 inspectée; ancienne URL officielle indexée mais HTTP 404 au rendu. Ne pas certifier la paire. Les dates d'édition ne sont pas les dates de mise en ligne. Aucune licence de reproduction attribuée; références et métadonnées uniquement. Aucun résultat de vote lu par le script.

Reproduction : `node experiments/municipal_v15/audit_catalog_pilot.mjs`. Six contrôles négatifs exécutés avec le même code dans l'environnement JS : doublon, même date, date impossible, langue dupliquée, date 2023+, admission non autorisée. CI du nouveau commit à vérifier.

## Backlog priorisé

1. V15.1b : échantillonner les autres dates indépendantes dans le manifeste de développement (sans lire les cibles), rechercher les preuves primaires contemporaines, URL et hashes par famille; comparer au corpus V11/V12, ne pas compter les traductions et les objets liés comme preuves indépendantes. Arrêter si couverture insuffisante ou texte redondant.
2. V15.2 : seulement si admission stricte, comparaison appariée texte technique vs brochure avec budget dimensionnel identique, et contrôle titre seul. Ajustements dans les plis temporels, métriques communale/centrée/nationale/cantonale, couverture, bootstrap par date, diagnostic; pas de sélection sur holdout. Risque élevé de réutilisation des dates de développement.
3. V13.2 et V14.1 : reprendre uniquement si nouvelle preuve de provenance/droits; aucun benchmark sur données en quarantaine.

Motivation : V13.5 oracle cantonal 3,7517 pp (scoring seul) contre V11.3 6,9558; des données nouvelles sont nécessaires, pas une calibration sur le scrutin cible. Pas de ciblage, données publiques agrégées uniquement.

## V15.1b — Deux dates supplémentaires, métadonnées seulement

CI du pilote V15.1a : [45824937943](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45824937943), 3/3 jobs réussis. Extension ciblée sur le 7 mars et le 13 juin 2021, six dossiers (session de juin complète, mars partiel), non aléatoire. La jointure au panel fixe reste à vérifier avant toute admission. Les dates d'année seule sont bornées au 31 décembre, les documents monolingues sont acceptés comme candidats (pas de traduction inventée). Les exclusions non neutres restent en place. Résultats exécutés :

```json
{
  "new_objects": 6,
  "new_dates": 2,
  "new_entries": 23,
  "new_object_family_pairs": 13,
  "new_distinct_families": 12,
  "new_year_precision_pairs": 1,
  "new_single_language_pairs": 3,
  "combined_objects": 13,
  "combined_dates": 5,
  "combined_candidate_objects": 12,
  "combined_entries": 57,
  "combined_object_family_pairs": 30,
  "combined_distinct_families": 27,
  "evidence_families": 9,
  "training_rows_admitted": 0,
  "negative_controls_passed": 10
}
```

Les deux dossiers agricoles contiennent des URLs différentes pour un document dont les premières pages rendues sont visuellement identiques. Une seule famille provisoire, deux associations. Le rapport de consultation PMT existe sur le serveur officiel et dans Swissvotes : les couvertures correspondent (été 2018), sans preuve binaire ni date de première mise en ligne. Sept fiches CO2 correspondent par titre au dossier officiel du DETEC; le communiqué du 29 mars 2021 atteste le contexte, pas la disponibilité exacte de chaque pièce. Liens et limites dans [le manifeste](../../../data/external/institutional_v151/catalog_extension_v151b.json). Aucun texte intégral, résultat de scrutin ni donnée individuelle exporté. La couverture est celle de l'échantillon, pas du panel 66 objets. Pas de nouveau score.

Reproduction : `node experiments/municipal_v15/audit_catalog_extension.mjs`. Dix contrôles négatifs exécutés. Prochain jalon : établir les hashes et preuves contemporaines de publication des paires officielles, vérifier droits et jointure au panel; mesurer recouvrement avec corpus existant avant de poursuivre l'inventaire. Si les sources restent bloquées, suspendre V15.1 et reprendre une piste prédictive indépendante sur données déjà admises. Aucun accès test final.

## V15.1c — audit binaire lancé, verrou juridique explicite

CI V15.1b [45835239455](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45835239455) : 3/3 jobs réussis. Les [conditions d'utilisation fédérales](https://www.admin.ch/fr/conditions-utilisation), section droits d'auteur, réservent la reproduction à une autorisation du titulaire : accès public ne signifie pas licence. Les exceptions légales et autorisations propres à chaque fichier restent à établir. Le [communiqué du 22.05.2019](https://www.ejpd.admin.ch/fr/nsb?id=75156) corrobore l'adoption du message MPT, non la date de publication de l'annexe exacte. Le rapport officiel (35 pages, couverture été 2018) a été consulté; aucun contenu individuel, aucun résultat de scrutin, aucun texte intégral conservé. Téléchargement direct local impossible (curl 6, DNS). Mise en place d'un job CI limité à trois paires déjà identifiées (AVS, MPT, doublon agricole), six requêtes maximales, timeout 30 s par requête, 15 MiB maximum, contrôle signature PDF, SHA-256 et taille. Aucun PDF exporté; seules les métadonnées et empreintes sont produites. 8 contrôles synthétiques exécutés avec les fonctions du script. L'identité réelle reste à vérifier dans le job; les échecs seront enregistrés sans imputation. Aucun accès aux cibles, aucune admission, aucun nouveau score. Après clôture du job, suspendre V15.1 si les droits restent non établis et revenir à une expérience indépendante sur données déjà admises. Jointure au panel et redondance textuelle non réalisées.
