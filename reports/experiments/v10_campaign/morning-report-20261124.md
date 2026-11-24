# Bilan du 24 novembre 2026 — campagne V10

Objectif : 4 pp MAE communale. Référence V8.1 7.2295 pp ; meilleur exploratoire V9 7.1319 pp. 66 objets, 23 dates, 138 868 observations, fenêtres 2016–18, 2019–20, 2021–22. Les expériences V10 sont comparées indépendamment à V8.1, pas cumulativement. Cinq étapes sur dix ont des résultats ; aucune ne dépasse V9. Validation de développement réutilisée, non indépendante ; aucun modèle promu.

## Toutes les configurations mesurées

Les scores ci-dessous sont les résumés consignés précédemment depuis les journaux des benchmarks réussis, avec métadonnées des artefacts. Les fichiers par objet/pli/canton et prédictions se trouvent dans les artefacts liés. Les ZIP ne sont pas réextraits ici. MAE en points de pourcentage. Gain positif = amélioration par rapport à V8.1 ; intervalle descriptif bootstrap par date, non corrigé pour sélection multiple.

### V10.1 — pilot

[Benchmark 45299149349](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45299149349) · [Artefact 14878720344](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45299149349/artifacts/14878720344) · tests ciblés : voir rapport · contrôle dépôt : failure.

| Variante | Commune | Centrée | Canton | Suisse | IC gain |
|---|---:|---:|---:|---:|---|
| reference | 7.2295 | 5.3701 | 5.7037 | 3.7757 | [0.0000, 0.0000] |
| expectation25 | 7.1827 | 5.3701 | 5.6416 | 3.6692 | [0.0000, 0.1325] |
| expectation50 | 7.1708 | 5.3701 | 5.6244 | 3.6853 | [-0.0186, 0.2027] |
| expectation75 | 7.1945 | 5.3701 | 5.6670 | 3.7624 | [-0.1123, 0.2312] |
| expectation100 | 7.2515 | 5.3701 | 5.7432 | 3.9095 | [-0.2627, 0.2056] |
| walk_forward | 7.1708 | 5.3701 | 5.6244 | 3.6853 | [-0.0186, 0.2027] |

### V10.1 — extension

[Benchmark 45301813438](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45301813438) · [Artefact 14879571160](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45301813438/artifacts/14879571160) · tests ciblés : 4 · contrôle dépôt : success.

| Variante | Commune | Centrée | Canton | Suisse | IC gain |
|---|---:|---:|---:|---:|---|
| reference | 7.2295 | 5.3701 | 5.7037 | 3.7757 | [0.0000, 0.0000] |
| expectation25 | 7.2145 | 5.3701 | 5.6634 | 3.8082 | [-0.1066, 0.1464] |
| expectation50 | 7.3003 | 5.3701 | 5.7611 | 4.0263 | [-0.3515, 0.2049] |
| expectation75 | 7.4728 | 5.3701 | 5.9841 | 4.3054 | [-0.7031, 0.1852] |
| expectation100 | 7.7173 | 5.3701 | 6.2871 | 4.7083 | [-1.1557, 0.1223] |
| walk_forward | 7.2495 | 5.3701 | 5.7052 | 3.9384 | [-0.2024, 0.1694] |

### V10.2 — pilot

[Benchmark 45309363603](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45309363603) · [Artefact 14882172985](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45309363603/artifacts/14882172985) · tests ciblés : 4 · contrôle dépôt : success.

| Variante | Commune | Centrée | Canton | Suisse | IC gain |
|---|---:|---:|---:|---:|---|
| reference | 7.2295 | 5.3701 | 5.7037 | 3.7757 | [0.0000, 0.0000] |
| bias_control | 7.2553 | 5.3701 | 5.7115 | 3.7634 | [-0.0913, 0.0167] |
| tone | 7.2584 | 5.3701 | 5.7146 | 3.7627 | [-0.0882, 0.0103] |
| tone_volume | 7.2600 | 5.3701 | 5.7156 | 3.7721 | [-0.0873, 0.0082] |
| tone_prominence | 7.2589 | 5.3701 | 5.7148 | 3.7633 | [-0.0914, 0.0117] |

### V10.2 — extension

[Benchmark 45309749540](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45309749540) · [Artefact 14882292438](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45309749540/artifacts/14882292438) · tests ciblés : 4 · contrôle dépôt : success.

| Variante | Commune | Centrée | Canton | Suisse | IC gain |
|---|---:|---:|---:|---:|---|
| reference | 7.2295 | 5.3701 | 5.7037 | 3.7757 | [0.0000, 0.0000] |
| bias_control | 7.2930 | 5.3701 | 5.7343 | 3.8683 | [-0.1830, 0.0440] |
| tone | 7.2945 | 5.3701 | 5.7424 | 3.8947 | [-0.2020, 0.0627] |
| tone_volume | 7.2271 | 5.3701 | 5.6743 | 3.8250 | [-0.1344, 0.1598] |
| tone_prominence | 7.2978 | 5.3701 | 5.7476 | 3.8988 | [-0.2042, 0.0616] |

### V10.3 — benchmark

[Benchmark 45316679885](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45316679885) · [Artefact 14884454967](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45316679885/artifacts/14884454967) · tests ciblés : 3 · contrôle dépôt : success.

| Variante | Commune | Centrée | Canton | Suisse | IC gain |
|---|---:|---:|---:|---:|---|
| reference | 7.2295 | 5.3701 | 5.7037 | 3.7757 | [0.0000, 0.0000] |
| eligible_only | 7.2295 | 5.3701 | 5.7055 | 3.7763 | [0.0000, 0.0000] |
| last_weights_only | 7.2295 | 5.3701 | 5.7178 | 3.7936 | [0.0000, 0.0000] |
| last_reanchor | 7.2169 | 5.3758 | 5.7052 | 3.7757 | [-0.0282, 0.0494] |
| pooled_weights_only | 7.2295 | 5.3701 | 5.7090 | 3.7710 | [0.0000, 0.0000] |
| pooled_reanchor | 7.2309 | 5.3750 | 5.7167 | 3.7757 | [-0.0225, 0.0183] |
| domain_reanchor | 7.2286 | 5.3757 | 5.7163 | 3.7757 | [-0.0232, 0.0237] |

### V10.4 — benchmark

[Benchmark 45323525729](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45323525729) · [Artefact 14888717635](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45323525729/artifacts/14888717635) · tests ciblés : 4 · contrôle dépôt : success.

| Variante | Commune | Centrée | Canton | Suisse | IC gain |
|---|---:|---:|---:|---:|---|
| reference | 7.2295 | 5.3701 | 5.7037 | 3.7757 | [0.0000, 0.0000] |
| additive_ridge | 7.2357 | 5.3618 | 5.7285 | 3.7757 | [-0.1665, 0.1538] |
| crossed_ridge | 7.2385 | 5.3648 | 5.7304 | 3.7757 | [-0.1762, 0.1565] |
| domain_ridge | 7.2537 | 5.3864 | 5.7446 | 3.7757 | [-0.1903, 0.1452] |
| margin_ridge | 7.2039 | 5.3249 | 5.6974 | 3.7757 | [-0.1373, 0.1880] |
| domain_pooled_weights | 7.2544 | 5.3864 | 5.7457 | 3.7710 | [-0.1912, 0.1451] |

### V10.5 — benchmark corrigé (ajout après rédaction du rapport du matin)

[Benchmark 45344880395](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45344880395) · [Artefact 14897029894](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45344880395/artifacts/14897029894) · 5 tests ciblés réussis · [CI générale réussie](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45344880448).

| Variante | Commune | Centrée | Canton | Suisse | IC gain |
|---|---:|---:|---:|---:|---|
| reference | 7.2295 | 5.3701 | 5.7037 | 3.7757 | [0.0000, 0.0000] |
| pooled_weights_control | 7.2295 | 5.3701 | 5.7090 | 3.7710 | [0.0000, 0.0000] |
| absolute25 | 7.3232 | 5.3766 | 5.8221 | 4.2014 | [-0.3689, 0.1792] |
| absolute50 | 7.9399 | 5.4351 | 6.5669 | 5.2186 | [-1.3149, -0.1020] |
| centered25 | 7.2441 | 5.3802 | 5.7010 | 3.7710 | [-0.0534, 0.0242] |
| centered50 | 7.3027 | 5.4439 | 5.7357 | 3.7710 | [-0.1539, 0.0082] |
| centered100 | 7.5367 | 5.7238 | 5.9581 | 3.7710 | [-0.4919, -0.1252] |

## Analyse

- V10.1 : 37 observations, 20 objets (pilote 9). Le gain du pilote n'est pas confirmé par l'extension. 25 % d'anticipations : gain 0.0150 pp, national dégradé, contraste inchangé. Ne pas promouvoir.
- V10.2 : 54 objets / 19 dates (pilote 24). Tonalité + volume : gain 0.0024 pp, non robuste ; dynamique entre instantanés non testée. Sources rétrospectives non certifiées, pas de hash des PDF originaux.
- V10.3 : variation totale des poids de bulletins 4.9996 → 3.0518 pp avec moyenne régularisée, soit environ 39 % de baisse. Participation 12.8259 → 9.1469 pp vs dernière participation. Conserver les poids alternatifs pour les essais hiérarchiques, pas de gain robuste des parts de oui.
- V10.4 : margin_ridge améliore la MAE centrée de 0.0451 pp et la MAE communale de 0.0257 pp, intervalle traversant zéro. 62 objets corrigés. Analogue agrégé, pas une MRP complète ; absence de distributions conjointes et de microdonnées.
- V10.5 : deux échecs avant scoring, puis benchmark corrigé réussi. Meilleure variante active centered25 : 7,2441 pp contre 7,2295 pour V8.1 ; les poids seuls laissent la MAE communale inchangée. Aucun gain robuste. Voir [résultats](V10.5-results.md) et [protocole](V10.5-protocol.md). V10.6 à V10.10 non évaluées.

## Limites et suite recommandée

Les 138 868 lignes ne sont pas 138 868 objets indépendants : seulement 66 objets de test, 23 dates. MAE centrée V8.1 5.3701 pp (on retire le biais moyen communal observé par objet pour ce diagnostic seulement), donc même une correction parfaite du décalage moyen ne suffit pas à justifier l'objectif de 4. Les oracles rétrospectifs ne sont pas des prévisions. Le niveau national est celui des communes admises, non nécessairement le total officiel ; poids de prévision ex-ante, vrais bulletins uniquement pour scoring. Référentiel géographique 2026 et versions historiques non certifiées : aucune revendication prospective stricte. Comparer poids communs et propres dans artefacts V10.3/4. Aucun résultat 2023+ pour sélection ou évaluation, pas de déploiement.

Reprendre à V10.6 (covariance régularisée sur prévisions strictement antérieures), V10.7 (kernel/GP sur profils agrégés), V10.8 (brochures vérifiées et effets sémantiques), V10.9 (données économiques millésimées et interactions), V10.10 (ensemble chronologique). Les gains faibles de V10.1–5 ne prouvent pas une limite théorique. L'objectif nécessite encore 3.1319 pp de réduction par rapport à V9 ; privilégier les modèles de structure géographique, puis vérifier sur un ensemble indépendant non utilisé pour le développement. Aucun résultat futur promis.
