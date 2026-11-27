# V20 — Biais résiduels historiques (27 novembre 2026)

V10 10/10. V8.1 gelée 7,229527497606818 pp ; V9 7,131910681945383 pp ; V11.3 meilleur exploratoire 6,955753873756506 pp. 66 objets, 23 dates, 138868 lignes 2016–2022. Aucun test final.

## V20.1 — Protocole avant résultat

V13.5 a montré une forte composante entre et intra-canton. V18.3 a rejeté la simple modification d'amplitude. Hypothèse distincte : un biais **signé additif** stable des erreurs OOF du modèle V11.3 peut être estimé sur les seules dates précédentes. V10.4 ajustait des cellules langue/urbanité sur V8.1 ; V10.5 prédisait directement des niveaux cantonaux ; ici, ni nouveau modèle de niveau ni modification d'amplitude, seulement intercepts géographiques résiduels sur la référence récente.

Quatre variantes : contrôle exact, intercept canton, intercept commune, somme canton + résidu intra-canton. Retirer d'abord la moyenne non pondérée des résidus par objet passé, puis moyenne par canton et résidu local. Agréger par date (moyenne des objets disponibles), régulariser chaque clé avec cinq pseudo-dates à zéro ; quatre dates de warm-up, aucune sélection de coefficients. Clés manquantes à zéro. Tous les objets du jour sont prédits avant mise à jour de l'historique. Conserver le niveau national pondéré ex ante via shift_to. Géographie indépendante fixe 2026 comme V18.3, limite as-of explicite. Pas de cible 2023+, données agrégées uniquement. Contrôle exact de hash et métrique de V11.3, quatre métriques, couverture, erreurs par objet/date/pli/domaine/canton/commune, bootstrap apparié date. Aucune prédiction de résultat individuel ni ciblage. Les dates réutilisées ne permettent pas d'inférence prospective. La sélection préalable de V11.3 sur ces mêmes dates reste un biais.

Reproduction : workflow V20.1 sur artefact v113-procedure du run 45444093555. Tests synthétiques : centrage intra-canton, warm-up, rétrécissement, clé inconnue, exclusion même date, bornes et ancre. Résultat et CI à vérifier.

## Backlog priorisé

1. Mesurer V20.1, analyser différences appariées et hétérogénéité ; aucun réglage opportuniste si échec.
2. Si échec, privilégier une méthode de représentation d'objet indépendante (informations déjà admises), ou un audit ciblé d'une source avec preuve de publication et de droits ; éviter répétition de V11–V19.
3. V19.3b, Fedlex et autres sources en quarantaine seulement sur preuve nouvelle.
