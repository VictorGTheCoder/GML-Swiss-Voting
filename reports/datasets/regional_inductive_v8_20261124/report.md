# V8 — Sondages linguistiques et modèles inductifs de profils communaux

## Résultat

**Meilleure MAE exploratoire : 7,340163035010155 pp**, contre 7,618292700184025
pour V3 et 7,547181283176325 pour V7. Le meilleur modèle conserve la
PCA5 temporelle (demi-vie 5 ans sur la base seule, têtes uniformes) et le
niveau national V3 ancré avec la tendance gelée. Il corrige les contrastes
régionaux par les dernières intentions parmi les électeurs décidés.
Aucun modèle de production ni prévision prospective remplacé.

Sur les 24 objets disposant de nouvelles marges, la MAE passe de 6,9891
à 6,4198 (gain de 0,5693 pp). Sur les 66 objets, gain de 0,2070 vs V7.
L'intervalle bootstrap descriptif apparié par date (gain V7 moins V8)
est [0,0623 ; 0,3785] pp. La sélection multiple et les fenêtres déjà
explorées empêchent d'en déduire un gain prospectif garanti.

## Protocole commun

66 objets, 23 dates, 138 868 observations communales, 2016–2022 ;
les trois fenêtres historiques et les paramètres V3 de l'ancre sont
conservés. Toutes les communes et les objets sans sondages restent
dans la MAE macro-objets. Aucun résultat 2023+ lu par les benchmarks.
Les éditions historiques des sources et la géographie fixe 2026 ne
sont pas certifiées. Statut : strict_forecast_ready=false.

## 1. Acquisition des marges linguistiques

Les rapports pré-vote SRG/gfs.bern publient des intentions par langue.
Leurs graphiques Infogram sont récupérés à partir des correspondances
exactes objet/date/vague/URL de la collecte nationale existante.
Chaque graphique doit reproduire les cinq catégories nationales déjà
auditées. Les lignes régionales sont identifiées par libellé linguistique
explicite et date de vague ; absence/ambiguïté est rejetée.

- 24 objets de 2021–2022, deux vagues possibles et trois régions.
- 135/144 lignes, 45 vagues complètes, 21 objets avec deux vagues,
  24 objets avec au moins une vague.
- Neuf lignes rejetées (6520 vague 1, 6550 vague 2, 6600 vague 2).
  Pas d'imputation des réponses ou d'invention d'un sondage.
- Valeurs brutes certaines/plutôt oui, indécis, plutôt/certainement non,
  URL, dates de terrain et publication, SHA-256 de la réponse graphique.
  Somme des cinq cellules arrondies admise 98–102 ; valeurs conservées.
- L'édition courante n'est pas certifiée historiquement, plusieurs
  graphiques ont un horodatage de modification postérieur au vote.
  L'archive officielle permet de retrouver les valeurs actuelles,
  pas de prouver leur identité à la version publiée à l'époque.

[Collecte versionnée](../../../data/external/polls_regional_v8/regional_polls.csv).
[Preuve brute des cellules source et rejets](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45288455195/artifacts/14872997781).

Les rapports de 2018 et 2020 retrouvés dans Année politique suisse
contiennent également des graphiques linguistiques :
[2018](https://anneepolitique.swiss/references/269382/download?filename=SRG-Trendumfrage+vom+19.2.18+_141_20180219.pdf&inline=true),
[2020](https://anneepolitique.swiss/references/454897/download?filename=SRG-Umfrage+vom+14.9.20_142_20200914.pdf&inline=true&locale=fr).
La récupération visuelle des graphiques PDF n'a pas abouti ; les
valeurs anciennes n'ont pas été transcrites depuis un texte PDF ambigu.
Elles constituent une possibilité d'extension, pas une collecte achevée.
Les autres sous-groupes Infogram (p. ex. agglomérations) sont visibles
dans l'inventaire, mais leur correspondance exacte aux typologies OFS
n'est pas établie ; aucun chiffre issu d'un appariement supposé n'est
injecté. Les rapports gfs.bern précisent que les effectifs ne permettent
pas une ventilation fiable pour la plupart des cantons.
Exemple : [rapport du 26 septembre 2021](https://cockpit.gfsbern.ch/fr/cockpit/srg_trend_26092021_fr/).

## 2. Factorisation inductive

Réutiliser la tête globale V3 et apprendre le profil communal à partir
des caractéristiques d'objet. Modèles : Kernel Ridge multivarié linéaire
et RBF, factorisation supervisée à noyau linéaire/RBF/mixte, rangs 5/10/20,
trois niveaux de régularisation pour les noyaux complets, deux variantes
itératives de complétion des cellules manquantes. Prétraitement et géométrie
des noyaux ajustés au train. La base latente supervisée maximise la
variation prédictible à partir des caractéristiques, contrairement à PCA
qui maximise la seule variation historique.

La sélection imbriquée utilise deux blocs chronologiques de quatre ans
antérieurs à chaque fenêtre externe ; critère d'erreur locale centrée.
Le modèle externe est réentraîné sur tout son train. Le niveau global
et l'ancre sont identiques pour toutes les variantes. Les deux références
V3 et V7 sont reproduites exactement.

| Configuration | MAE finale | MAE centrée locale |
| --- | ---: | ---: |
| V3 référence | 7,6183 | 5,6986 |
| V7 PCA récente | **7,5472** | **5,6115** |
| Linéaire complet lambda=.03 | 9,5759 | 8,0487 |
| Linéaire complet lambda=.3 | 8,2000 | 6,5018 |
| Linéaire complet lambda=3 | 7,8704 | 6,0795 |
| RBF complet lambda=.03 | 8,4970 | 6,6048 |
| RBF complet lambda=.3 | 8,2779 | 6,2918 |
| RBF complet lambda=3 | 8,2084 | 6,2516 |
| Linéaire rang 5 | 7,7581 | 5,9600 |
| Linéaire rang 10 | 7,7728 | 5,9772 |
| Linéaire rang 20 | 7,8808 | 6,1179 |
| RBF rang 5 | 8,1979 | 6,2319 |
| RBF rang 10 | 8,1602 | 6,1677 |
| RBF rang 20 | 8,1761 | 6,1878 |
| Mixte rang 10 | 7,7352 | 5,8592 |
| Linéaire rang 10, complétion | 7,7739 | 5,9780 |
| RBF rang 10, complétion | 8,1604 | 6,1677 |
| Choix imbriqué | 8,1855 | 6,2334 |

Choix imbriqués RBF rang 5, rang 10, rang 10. Aucune factorisation
testée ne dépasse V7 ; ceci ne démontre pas l'impossibilité de toute
factorisation inductive. Les caractéristiques d'objet actuelles ne
fournissent pas assez de signal transférable pour ces modèles.
Les trois modèles (V3, V7, choix imbriqué) sont conservés au niveau
communal et réutilisés dans l'expérience régionale.

## 3. Correction régionale, méthodes et résultats

Corriger la différence entre les marges linguistiques plutôt que
leur niveau absolu permet de conserver exactement l'ancre nationale
pondérée par le proxy de population électorale. Les communes romanches
ou non classées gardent leur niveau dans les méthodes de correction
directe. Les marges sont recalées par décalage borné sur [0,1].
On teste la dernière vague, l'extrapolation régionale bornée,
les indécis, les forces d'ancrage 25/50/100 %, l'ajustement absolu
et un opérateur latent de covariance historique (ridge). Une sélection
en ligne utilise uniquement les dates déjà terminées.
Les effectifs opt-in ne sont pas assimilés à des effectifs statistiques
indépendants ; la régularisation est exploratoire.

| V7 + correction | MAE 66 objets | MAE 24 objets couverts |
| --- | ---: | ---: |
| Nationale seule | 7,5472 | 6,9891 |
| Dernière vague 25 % | 7,4598 | 6,7488 |
| Dernière vague 50 % | 7,3973 | 6,5769 |
| Dernière vague 100 % | 7,3521 | 6,4527 |
| Tendance régionale 25 % | 7,4768 | 6,7955 |
| Tendance régionale 50 % | 7,4552 | 6,7362 |
| Tendance régionale 100 % | 7,5309 | 6,9444 |
| Décidés 50 % | 7,3870 | 6,5487 |
| Décidés 100 % | **7,3402** | **6,4198** |
| Moitié des indécis 50 % | 7,3916 | 6,5611 |
| Absolue dernière 50 % | 7,4421 | 6,7003 |
| Absolue tendance 50 % | 7,5124 | 6,8935 |
| Latente dernière 50 % | 7,4254 | 6,6543 |
| Latente dernière 100 % | 7,4229 | 6,6474 |
| Latente tendance 50 % | 7,4925 | 6,8388 |
| Latente tendance 100 % | 7,6436 | 7,2544 |
| Choix en ligne | 7,3580 | 6,4689 |

V3 + dernière marge décidés à 100 % = 7,4100.
Meilleure combinaison du modèle inductif imbriqué = 7,8841
(ancrage latent dernière vague à 100 %). La combinaison inductive
reste inférieure à V7 + sondages régionaux.

## 4. Oracles géographiques (NON prévisions)

Les décalages médians rétrospectifs utilisent les résultats connus et
ne doivent jamais alimenter les prédicteurs. Ils isolent le potentiel
de chaque échelle. Le diagnostic par canton inclut des groupes parfois
très petits : il ne s'agit pas d'une borne d'erreur opérationnelle.

| Correction oracle V7 | MAE |
| --- | ---: |
| Décalage national optimal | 5,5255 |
| Décalages linguistiques | 4,3171 |
| Langue × urbanisation | 4,1325 |
| Décalages cantonaux | **3,7638** |
| Contrastes linguistiques exacts, ancre nationale inchangée | 6,6290 |
| Contrastes cantonaux exacts, ancre nationale inchangée | 6,1271 |

Le diagnostic cantonal montre la capacité des profils existants lorsque
les niveaux territoriaux sont connus. Il ne démontre ni que des sondages
cantonaux sont disponibles, ni que l'objectif 4 est atteint. La mauvaise
estimation du niveau global demeure également importante.

## 5. Calibration chronologique nationale et régionale

21 combinaisons : sept traitements nationaux (gelé, dernière vague,
décidés avec/sans tendance, moitié des indécis + tendance, correction
de biais régularisée et régression bornée de la tendance/des indécis)
× trois traitements régionaux (aucun, contrastes décidés, contrastes
empiriquement recalibrés). Les calibrateurs voient exclusivement des
scrutins antérieurs au jour prévu ; au moins huit objets avant ajustement.
La mise à jour après une date entière est distincte du gel des têtes
structurelles dans les grandes fenêtres. Aucune information du même
jour dans l'apprentissage.

| Traitement national | Sans régional | Avec contrastes décidés | Régional empirique |
| --- | ---: | ---: | ---: |
| Gel V3 | 7,5472 | **7,3402** | 7,3778 |
| Dernière vague | 8,4568 | 8,2798 | 8,3070 |
| Décidés dernière vague | 8,8671 | 8,7144 | 8,7408 |
| Décidés + tendance | 7,5699 | 7,3708 | 7,4057 |
| Moitié indécis + tendance | 7,5992 | 7,3975 | 7,4347 |
| Biais régularisé | 7,6031 | 7,3938 | 7,4305 |
| Régression bornée | 7,6035 | 7,3972 | 7,4338 |

La tendance nationale gelée reste le meilleur compromis dans cette grille.
L'ancrage régional utilise les décidés pour les **écarts**, mais leur part
au niveau national ne remplace pas automatiquement le bon estimateur
de la tendance. Les objets sans sondage (18) restent à 8,7204 dans V7/V8.

## Décision et limites

Le score 7,3402 est le meilleur observé du projet sur ce développement,
soit -0,2781 pp vs V3. Il n'est pas promu comme candidat indépendant.
Priorités 1 et 2 seulement : poursuivre la couverture historique des
marges, les contrastes géographiques conditionnés par des observations
pré-vote plus informatives, et la validation prospective séparée.
La couverture actuelle concerne 24/66 objets. Il serait incorrect de
présenter le score de 6,4198 sur ce sous-ensemble comme le score général,
ou d'extrapoler le gain aux autres dates sans données.

## Preuves reproductibles

- [Acquisition](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45288455195).
- [Factorisation inductive](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45288455272),
  [artefact](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45288455272/artifacts/14872023926).
- [Ancrage et oracles](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45288754517),
  [artefact](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45288754517/artifacts/14871784371).
- [Calibration](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45289131737),
  [artefact](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45289131737/artifacts/14873975333).

Les campagnes dédiées ont toutes réussi. Tests ciblés : noyaux
et rang, invariance aux requêtes, cohérence nationale, publications
admissibles et calibration de petit échantillon. Les fichiers de
résultats conservent les métriques par objet et les manifestes.
