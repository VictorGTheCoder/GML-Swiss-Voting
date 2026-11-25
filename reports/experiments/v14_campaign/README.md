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
