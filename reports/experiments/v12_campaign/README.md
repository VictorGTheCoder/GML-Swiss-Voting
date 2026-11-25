# V12 — qualité et couverture des textes (25 novembre 2026)

Suite de [V11](../v11_campaign/README.md) et [V10](../v10_campaign/README.md). Meilleur exploratoire V11.3 : 6,955753873756506 pp. V8.1 gelée 7,229527497606818 ; V9 historique 7,131910681945383 ; V10.8 6,988599997055331. 66 objets / 23 dates / 138868 lignes 2016–2022. Aucun résultat cible 2023+ dans fit/calibration/scoring. Données publiques agrégées, pas de ciblage, pas de modèle promu. Objectif scientifique 4 pp, pas de critère de livraison.

## V12.1 — Protocole préspécifié

V11.2 réduit la couverture brute de 59 à 41 objets, donc son échec ne distingue pas qualité et couverture. L'expérience conserve le pipeline V10.8 (trois fenêtres, PCA5, demi-vie 5 ans, TF-IDF 16, ancres et poids gelés) et ne change que le corpus. Les masques utilisent uniquement la disponibilité des documents (pas les scores ni les résultats) sur chaque objet, aussi dans le train. Le vocabulaire et les projections sont ajustés uniquement dans le train. Comparer :
- matched_original : corpus initial sur l'intersection des couvertures, titre seul ailleurs ;
- matched_exact : première page auditée sur la même intersection, titre seul ailleurs ;
- title_only : contrôle sans texte ;
- union_prefer_exact : page exacte si disponible, sinon ancien texte couvert, sinon titre.
- Références figées V8.1, V10.8 et V11.3 sur les mêmes lignes.

Hypothèse falsifiable : la page exacte apporte un gain par rapport à matched_original si le contenu, plutôt que sa simple disponibilité, est déterminant ; l'union teste séparément une politique de repli pragmatique. Les textes d'origine restent des candidats rétrospectifs non certifiés, pas une source strictement as-of. Ne pas présenter les pages non confirmées comme incorrectes. Exporter la liste des lacunes (identité, date, titre, indicateurs de couverture), les métriques multi-échelles et bootstrap apparié par date, et les diagnostics par objet/pli/domaine/commune/canton. Aucun choix rétrospectif ne vaut validation prospective. Résultats à vérifier dans Actions.

## Backlog
1. V12.1 : ablation appariée et inventaire des lacunes (implémentation initiale, benchmark non vérifié).
2. V12.2 : récupérer par objet les documents officiels manquants et les correspondances de pages ambiguës ; enregistrer URL, date, identité, SHA-256, licence et limites d'archive ; refuser les textes post-vote ou non vérifiables.
3. V12.3 : tester représentation de plusieurs enjeux et sens du texte, avec ablation couverture égale, sans variables de ciblage.
4. V12.4 : contrôler robustesse des gains et complémentarité avec les signaux institutionnels, puis définir protocole final distinct (sans exécuter le holdout sans autorisation).
