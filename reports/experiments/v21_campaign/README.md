# V21 — Contexte ex ante de la session (27 novembre 2026)

Suite de [V20](../v20_campaign/README.md). V10 10/10 ; V8.1 gelée 7,229527497606818, V9 7,131910681945383, meilleur exploratoire V11.3 6,955753873756506 pp. 66 objets / 23 dates / 138868 lignes 2016–22. Aucun test final.

## V21.1 — Protocole fixé avant mesure

V20.2 ne montre aucun gain : abandon des corrections résiduelles. Les objets ne sont pas présentés isolément au niveau institutionnel : tester si la composition de la session (connue avant le scrutin) contient de l'information supplémentaire sur la forme du résultat agrégé. Ce n'est ni une nouvelle source ni un signal de campagne. V3 avait déjà testé le nombre d'objets dans un bloc, ici il sert de contrôle isolé. Aucun résultat de vote, participation réelle, ou donnée individuelle dans les caractéristiques de contexte.

Trois configurations entraînées avec exactement les paramètres V11.3, mêmes trois fenêtres, PCA5, TF-IDF16, ancres et poids : institution_replay (contrôle exact exigé par ligne), session_count (nombre d'autres objets), session_peers (nombre et moyenne des quatre indicateurs institutionnels des autres objets, leave-one-out, valeurs manquantes conservées avec indicateurs). Le roster provient des seules colonnes de date/identité/procédure Swissvotes déjà utilisées, non du nombre de lignes ou d'objets présents dans le panel communal. Décisions parlementaires strictement antérieures au scrutin via procedural_features. Pas d'utilisation du sens du vote populaire des autres objets ni de fit sur la date cible. Les caractéristiques des autres objets du jour sont ex ante, pas leurs cibles. Date de publication précise de l'édition rétrospective non certifiée : limite V11.3 inchangée ; ni modèle strictement prospectif, ni revendication de gain indépendant.

Hypothèse falsifiable : contexte améliore le contrôle institutionnel et le simple comptage sur la même population. Contrôles de jointure clé/date, absence 2023+, invariance à l'ajout de cibles, singleton, valeurs manquantes et isolation des dates. Exporter quatre MAE, bootstrap apparié par date, couverture des objets avec pairs valides, diagnostics date/pli/domaine/canton/commune ; source et prédictions hachées. Aucun réglage après observation. Comparaison de référence V8.1 et V11.3, replay exact exigé. CI et benchmark à vérifier. Pas de nouvelle admission de données.

## Backlog priorisé

1. Mesurer V21.1, comparer compte et pairs au replay ; ne pas ajuster si échec.
2. Rechercher une source ex ante indépendante avec preuve de disponibilité et droits ; ne pas répéter les acquisitions en quarantaine sans nouvelle preuve.
3. Si les sources restent bloquées, privilégier une hypothèse de représentation indépendante, puis robustesse chronologique avant toute demande d'évaluation finale distincte.

## V21.1 — clôture

[Résultats](V21.1-results.md) : 6,9619 pp (comptage), 7,2060 pp (pairs), replay exact 6,9558. 4 tests ciblés, CI générale lint corrigé. Aucun gain. [V22](../v22_campaign/README.md) ouverte.
