# V17 — Signaux historiques indépendants

Suite de [V16](../v16_campaign/README.md), [V13](../v13_campaign/README.md), [V10](../v10_campaign/README.md). Références inchangées, V8.1 7,229527497606818 pp, V9 7,131910681945383 pp, V11.3 6,955753873756506 pp (66 objets/23 dates/138868 lignes 2016–22). Aucun test final.

## Backlog préliminaire

1. V17.1 : identifier une série institutionnelle ou territoriale agrégée indépendante, avec licence explicite, preuves d'édition historique et couverture utile ; rechercher en priorité une source primaire résolvant un blocage V13.2/V14.1/V15.1. Préenregistrer hypothèse, jointures, seuils de couverture et contrôles avant accès aux scores. Pas d'admission sur simple accès public.
2. V17.2 : sur données admises, ablation appariée et diagnostic de redondance dans les seules fenêtres d'entraînement ; mêmes métriques et bootstrap par date. Si aucune nouvelle preuve, sélectionner une autre source publique agrégée ou une hypothèse non dupliquée sur données autorisées.
3. V17.3 : audit de robustesse temporelle et d'incertitude du meilleur candidat exploratoire uniquement si un gain justifie la comparaison. Pas de sélection avec 2023+ ni de promotion. Éviter les mélanges de niveau déjà testés (V16.3) et les corrections déjà négatives (V10.5–6, V11.4, V12.4).

État : ouverture du registre, aucun benchmark V17 encore effectué. Les dates de développement répétées ne permettent pas de conclure à une généralisation inédite.

## V17.1 — ElCom

[Protocole et audit](V17.1-elcom-protocol.md) : source publique de tarifs communaux, conditions ouvertes explicites au niveau ressource ; 7 années ciblées, neuf contrôles synthétiques réussis. DNS local bloqué, acquisition via CI à vérifier. Zéro admission, aucun nouveau score. Priorité : couverture mesurée, géographie historique et preuve de version avant ablation ; ne pas relancer à l'identique en cas de blocage persistant. [Checkpoint](../../../experiments/municipal_v17/state.json).
