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

## Implémentation V19.1

Le script et son workflow ont été ajoutés. Les deux réponses sont comparées sur un multiensemble des six champs identifiants/date (ordre des lignes ignoré, multiplicité conservée), avec contrôles d'origine, schéma et SHA-256. Les résultats sont uniquement agrégés ; aucune ligne de vote ni donnée candidate exportée. La différence observée sera un diagnostic de couverture des mutations, pas une certification des frontières. Huit assertions synthétiques prévues ; résultat CI et audit réseau à vérifier. Aucun score nouveau.

## V19.1 mesurée / V19.2

[Résultats et protocole](V19.1-results-v192-protocol.md) : 414 contre 420 lignes ; six lignes ajoutées, zéro retirée, 233 identifiants distincts dans chaque réponse. CI 3/3. V19.2 implémentée, diagnostic des clés et de la date uniquement, sans admission ni score nouveau. V19.3 ensuite prioritaire.

## V19.2 clôturée / V19.3a

[Résultats](V19.2-results.md) : 12870/138868 lignes en recouvrement numérique (9,27 %), aucune différence des totaux avec échanges, 198 lignes recouvrent les six enregistrements supplémentaires. 12/12 assertions, CI 3/3. [V19.3a](V19.3a-deliberations-pilot.md) : 2 projets liés, 1 date, 8 contrôles, zéro admission ; vérifier couverture et provenance avant ablation. Aucun score nouveau.

## V19.3a — pilote structuré

[Protocole](V19.3a-structured-protocol.md) : une tentative OData bornée sur trois affaires, quatre collections, compteurs uniquement et 8 assertions réussies. Réseau à vérifier. Aucun score ni admission. En cas de blocage, suspendre et changer de piste.
