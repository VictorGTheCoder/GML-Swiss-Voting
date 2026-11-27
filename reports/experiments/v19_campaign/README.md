# V19 — Validité des jointures géographiques (27 novembre 2026)

[V18](../v18_campaign/README.md) clôturée sans gain. [V10](../v10_campaign/README.md) 10/10. V8.1 7,229527497606818 pp gelée, V9 7,131910681945383 pp, V11.3 meilleur exploratoire 6,955753873756506 pp, 66 objets / 23 dates / 138868 lignes 2016–2022. Aucun test final.

## V19.1 — audit des mutations, distinct de l'acquisition de covariables

Les audits V17 ont montré que l'identité numérique seule ne certifie pas les frontières et que l'ancien traitement excluait les échanges de territoire. V18.3 utilise la table géographique fixe 2026. Hypothèse falsifiable : les requêtes OFS avec et sans échanges de territoire ne sont pas équivalentes pour 2016–2022. Si elles diffèrent, mesurer ensuite l'incidence sur les seules clés du benchmark, sans résultats de vote. Ne pas qualifier une commune de stable sur la seule égalité de code. Les données publiées en 2026 ne seront jamais utilisées comme nouvelle variable ex ante ; l'audit rétrospectif sert uniquement à identifier les incohérences.

Sources : [catalogue OFS](https://opendata.swiss/en/dataset/historisiertes-gemeindeverzeichnis-der-schweiz), [documentation REST v2026.06.1, pp. 1–2](https://www.agvchapp.bfs.admin.ch/documents/rest_api_fr.pdf), [ressource mutations](https://opendata.swiss/de/dataset/historisiertes-gemeindeverzeichnis-der-schweiz/resource/2c57fcde-17cf-458b-965c-ae8f742a88a1). Documentation consultée ; appel direct via navigateur non accessible. Licence spécifique et versions historiques à confirmer avant toute redistribution/admission. La documentation distingue HistoricalCode et BfsCode, et décrit explicitement includeTerritoryExchange. La date de validité n'est pas une preuve de première publication.

## Registre et backlog

1. V19.1 : acquérir les deux réponses CSV du même intervalle 01.01.2016–31.12.2022, contrôler schéma, cardinalité, hash, différences exactes ; aucune cible lue, aucune admission. Échec réseau ou schéma : journaliser, pas de résultat inventé.
2. V19.2 : joindre les codes historiques aux dates du panel figé, distinguer changement de code, fusion et échange de territoire ; vérifier les dates de référence, ne pas remapper rétroactivement les cibles ni modifier les poids du benchmark. Si l'audit révèle une population différente, publier un diagnostic distinct.
3. V19.3 : après audit, prioriser une source d'information objet indépendante ou une architecture non répétée, avec ablation préenregistrée, validation chronologique imbriquée, métriques et bootstrap. Pas d'entraînement sur sources en quarantaine. Éviter les recalibrations V18 et les mélanges V16.3.

Aucun résultat V19 ni gain nouveau à ce stade.
