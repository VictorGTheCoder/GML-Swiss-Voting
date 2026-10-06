# Datasets Must du projet

Cette page fixe le socle de données retenu pour le **Must** du projet GML. Elle distingue les datasets utilisés directement pour construire la target et les features du modèle de la source technique nécessaire à l’harmonisation géographique.

## Datasets utilisés dans le Must

| Dataset / source | Ce qu’il apporte | Granularité | Années utiles | Variables principales |
|---|---|---|---|---|
| **OFS – Votations populaires, résultats au niveau des communes** | Dataset central du projet : target et historique électoral communal | Commune × votation | **1960–2026** | `yes_share`, oui/non, participation, inscrits, date, canton |
| **OFS – STATPOP** | Profil démographique de chaque commune | Commune × année | **2010–2025** | population, classes d’âge, part d’étrangers, éventuellement sexe |
| **OFS – Force des partis au Conseil national par commune** | Profil politique de la commune | Commune × élection | **2011, 2015, 2019, 2023** dans notre période | force UDC, PS, PLR, Centre, Verts, PVL, etc. |
| **Chancellerie fédérale – Explications du Conseil fédéral** | Décrire le contenu de l’objet soumis au vote avec une source officielle pré-scrutin | Votation / objet | **1978–2026** | titre, texte, arguments, recommandation du Conseil fédéral, nature de l’objet |
| **Swissvotes** | Caractérisation structurée de l’objet politique | Votation / objet | Couvre largement notre période | thème/domaine politique, type juridique, métadonnées de l’objet |
| **OFS – Typologies territoriales / région linguistique** | Décrire le contexte territorial de la commune | Commune | Versions historiques selon disponibilité | région linguistique, urbain/intermédiaire/rural, éventuellement typologie plus fine |

## Source technique d’harmonisation

| Source technique | Rôle | Granularité | Utilisation |
|---|---|---|---|
| **OFS – Répertoire historique et mutations des communes** | Harmoniser les différents référentiels communaux | Commune / mutation | gérer fusions, changements de numéro, absorptions, urnes communes et convertir les autres datasets vers la géographie de référence des votations |

Cette source est indispensable au pipeline de données mais n’est pas une feature ML en elle-même.

## Hors Must pour le moment

- **STATENT / structure économique** : Wish, à tester ultérieurement par ablation.
- **État civil** : hors socle initial, car largement redondant avec le bloc démographique STATPOP.

## Règle temporelle commune

Pour toute feature associée à une votation, utiliser uniquement une information réellement disponible **avant la date du scrutin**. Une année de référence antérieure ne suffit pas à garantir l’absence de fuite : la date de publication ou une règle conservatrice documentée doit être prise en compte.
