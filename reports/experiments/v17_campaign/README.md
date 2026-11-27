# V17 — Signaux historiques indépendants

Suite de [V16](../v16_campaign/README.md), [V13](../v13_campaign/README.md), [V10](../v10_campaign/README.md). Références inchangées, V8.1 7,229527497606818 pp, V9 7,131910681945383 pp, V11.3 6,955753873756506 pp (66 objets/23 dates/138868 lignes 2016–22). Aucun test final.

## Backlog préliminaire

1. V17.1 : identifier une série institutionnelle ou territoriale agrégée indépendante, avec licence explicite, preuves d'édition historique et couverture utile ; rechercher en priorité une source primaire résolvant un blocage V13.2/V14.1/V15.1. Préenregistrer hypothèse, jointures, seuils de couverture et contrôles avant accès aux scores. Pas d'admission sur simple accès public.
2. V17.2 : sur données admises, ablation appariée et diagnostic de redondance dans les seules fenêtres d'entraînement ; mêmes métriques et bootstrap par date. Si aucune nouvelle preuve, sélectionner une autre source publique agrégée ou une hypothèse non dupliquée sur données autorisées.
3. V17.3 : audit de robustesse temporelle et d'incertitude du meilleur candidat exploratoire uniquement si un gain justifie la comparaison. Pas de sélection avec 2023+ ni de promotion. Éviter les mélanges de niveau déjà testés (V16.3) et les corrections déjà négatives (V10.5–6, V11.4, V12.4).

État : ouverture du registre, aucun benchmark V17 encore effectué. Les dates de développement répétées ne permettent pas de conclure à une généralisation inédite.

## V17.1 — ElCom

[Protocole et audit](V17.1-elcom-protocol.md) : source publique de tarifs communaux, conditions ouvertes explicites au niveau ressource ; 7 années ciblées, neuf contrôles synthétiques réussis. DNS local bloqué, acquisition via CI à vérifier. Zéro admission, aucun nouveau score. Priorité : couverture mesurée, géographie historique et preuve de version avant ablation ; ne pas relancer à l'identique en cas de blocage persistant. [Checkpoint](../../../experiments/municipal_v17/state.json).

## V17.1a/b — Acquisition réussie et jointure

[Résultats et protocole de jointure](V17.1a-elcom-results.md) : 7/7 requêtes, 15656 commune-années brutes, 14471 à ligne unique ; 9/9 tests acquis. V17.1b mesure la couverture sur les clés exactes du benchmark, CI à vérifier. Les valeurs restent en quarantaine. V17.2 dépend de la géographie et des vintages certifiés ; sinon reprendre une piste indépendante sans relancer ces requêtes. Aucun nouveau score.

## V17.1b — correction de jointure

[Incident et correction](V17.1b-id-fix.md) : CI générale 3/3, couverture échouée sur format ID après huit tests réussis. Normalisation numérique stricte et garde d'injectivité ; 7 nouveaux contrôles à vérifier. La géographie fixe 2026 rend indispensable un audit distinct des mutations. Aucun résultat de couverture encore disponible, zéro admission.

## V17.1b — clôture et V17.2a

[Couverture mesurée](V17.1b-coverage-results.md) : 4/7 années au seuil de 90 % (5 requises), 90.44 % de lignes à ID unique, 15/15 tests. ElCom suspendue sans changer le seuil ni les frontières. [V17.2a](V17.2a-stru-candidate.md) : deux éditions OFS STRU OPEN-BY, données structurelles agricoles agrégées ; priorité aux publications contemporaines et contrôle de redondance STATENT. Zéro admission et aucun nouveau score.

## V17.2b — archives historiques

[Audit et protocole](V17.2b-stru-vintages.md) : deux éditions contemporaines OPEN-BY (2016 et 2018), une avec lien binaire explicite. Quatre autres dates de publications nationales confirmées sans cube historique certifié. 8 contrôles synthétiques réussis; acquisition via CI à vérifier. Zéro admission, aucun score. Priorité à la provenance et géographie avant couverture, sinon piste indépendante.

## V17.2b clôturée / V17.2c — disponibilité et géographie

[Résultats et protocole](V17.2b-results-v172c-protocol.md) : 1/2 binaires, 2016 HTTP 404, 2018 SHA vérifié et LAST-UPDATED cohérent avec 28.05.2019. 8/8 contrôles, CI 3/3. Plafond temporel 75768/138868 (54.56 %). Diagnostic des clés et notes géographiques préenregistré ; aucune admission, aucun nouveau score. V17.2c doit mesurer la disponibilité exacte et la couverture brute avant toute harmonisation. Ne pas relancer l'audit 2016 sans preuve nouvelle.

## V17.2c — incident et correction conservatrice

[Diagnostic de l'échec](V17.2c-geography-incident.md) : 12/12 contrôles, CI générale 3/3, mais désaccord entre label et code sur l'en-tête réel. Exclure conflits et doublons, mesurer séparément les IDs corroborés ; nouveau diagnostic à vérifier. Zéro admission, aucun score. Suspendre si géographie non certifiable.
