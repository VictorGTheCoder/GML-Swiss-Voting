# Variables politiques V2

Le module `scripts/modeling/political_features_v2.py` enrichit une table
commune × objet sans utiliser sa cible. Il complète les thèmes par les consignes
et les rapports de forces politiques. Une consigne de parti indique qui soutient
un objet ; elle ne constitue pas, à elle seule, une annotation de son effet sur
l'environnement, la redistribution ou une autre dimension de politique publique.

## Contrat

```python
from scripts.modeling.political_features_v2 import add_political_features

enriched, manifest = add_political_features(municipal_table, swissvotes)
numeric = manifest["numeric_features"]
categorical = manifest["categorical_features"]
object_numeric = manifest["object_numeric_features"]
object_categorical = manifest["object_categorical_features"]
```

L'index, l'ordre, les identifiants, les valeurs et les colonnes initiales sont
conservés. Les nouvelles colonnes commencent par `political_`. Les listes du
manifeste constituent la sélection autorisée ; passer la table enrichie entière
au modèle introduirait sa cible et ses métadonnées.

Le module vérifie les clés uniques commune × objet, les clés Swissvotes uniques,
la correspondance de chaque objet et l'égalité des dates. Il refuse une jointure
incomplète ou ambiguë, une question subsidiaire repérée par `rechtsform=5` et
l'écrasement de variables politiques déjà présentes. Les champs optionnels
absents restent manquants et sont recensés.

## Variables et encodage

| Groupe | Contenu |
|---|---|
| Consignes nationales | Neuf partis : PLR, PDC, PS, UDC, PEV, Verts, PVL, PBD et Centre. Catégorie distincte par code documenté. |
| Directions partisanes | +1 pour une consigne oui, −1 pour non ; NaN pour toute autre position ou absence. |
| Interactions communales | Direction × dernière force électorale locale fournie dans la table, en fraction 0–1. |
| Soutien communal observé | Masses électorales connues soutenant oui/non, couverture binaire, masse totale observée, masse sans consigne binaire, fraction oui parmi le soutien connu, nombre de partis sans force locale. |
| Institutions | Conseil fédéral, Parlement et chacune des deux chambres : catégorie et direction binaire. |
| Votes parlementaires | Oui / (oui + non) dans chaque chambre, lorsque les deux comptes sont valides et le total positif. |
| Soutien national | `ja-lager`, `nein-lager`, leur couverture et la fraction oui parmi ces soutiens connus, en fractions 0–1. |
| Thèmes détaillés | Six codes `d1e2`…`d3e3`, traités comme catégories nominales. |

Les listes `object_*` identifient explicitement les variables constantes par
objet. Les interactions et agrégats communaux n'y entrent jamais, même lorsqu'ils
seraient accidentellement constants sur un petit échantillon d'apprentissage.

Les codes de consigne 3, 4, 5, 66 et 9999 restent distincts : absence explicite
de recommandation, bulletin blanc, liberté de vote, neutralité historique et
organisation inexistante. Les codes 8 et 9 désignent une préférence entre
contre-projet et initiative ; ils ne deviennent pas un oui/non ordinaire. Une
valeur inconnue reste manquante. Les inconnues ne reçoivent pas une direction
numérique nulle.

Le Centre n'hérite automatiquement ni des scores électoraux ni des consignes du
PDC/PBD. Une telle continuité réclamerait une transformation séparée et justifiée.
La couverture des interactions peut donc être moindre pendant une transition.

Dans un agrégat de soutien, une contribution observée nulle signifie seulement
qu'aucun soutien explicite n'est connu pour cette composante. La couverture et
le nombre de forces locales manquantes permettent de distinguer cette situation
d'une opposition connue. Si aucune force locale n'est disponible, les masses
restent NaN. Si les forces sont connues mais qu'aucune consigne n'est binaire,
la couverture vaut zéro et la fraction oui reste NaN.

## Qualité et limites temporelles

Les recommandations correspondent à une information pré-vote par leur nature.
La copie actuelle de Swissvotes ne prouve cependant pas la disponibilité de
chaque valeur exacte à une date historique de prévision. Le manifeste conserve
donc `mode=exploratory_retrospective`, `strict_forecast_ready=false` et
`availability_status=historically_unverified`. Ce module ne modifie aucun
contrôle d'admissibilité de la V1 stricte.

L'empreinte du sous-ensemble de source utilisé, la liste des champs, les codes,
les valeurs rejetées et la couverture sont enregistrés. Les numériques invalides
deviennent manquants avec décompte ; aucune imputation apprise n'est faite ici.
Cette imputation et tous les encodages appris doivent rester dans l'entraînement
de chaque fenêtre temporelle.

Les champs de résultat, de participation, d'électorat courant, de financement,
de publicité et de tonalité médiatique sont absents de la liste source. Les
dissidences cantonales ne sont pas utilisées : un champ vide ne prouve pas
l'accord avec la consigne nationale. Les thèmes détaillés n'indiquent toujours
pas le sens de la mesure.

## Sources et vérification

- [Codebook officiel Swissvotes](https://swissvotes.ch/page/dataset/codebook-de.pdf),
  consulté le 23 novembre 2026 : institutions et votes parlementaires pp. 12–14 ;
  consignes et codes pp. 21–23 ; soutien électoral des camps pp. 26–28.
- Données : snapshot versionné `data/processed/swissvotes/swissvotes_clean.parquet`.
- Tests : `python -m pytest -q tests/test_political_features_v2.py`.

Les tests couvrent les codes non binaires et inconnus, l'identité des lignes,
les jointures erronées, les valeurs impossibles, les champs optionnels absents,
la transition des partis et l'invariance des nouvelles variables lorsqu'on
change les résultats ou ajoute des champs de campagne à la source.
