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
