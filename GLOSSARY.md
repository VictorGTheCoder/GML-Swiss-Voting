# Prédiction des votations fédérales suisses

Ce vocabulaire distingue les unités de votation et les conclusions permises par
les analyses du projet.

## Language

**Objet de votation** :
Question fédérale soumise au vote à une date donnée, distincte des autres questions
éventuellement soumises le même jour.
_Avoid_ : Date de votation pour désigner une question.

**Observation communale** :
Résultat d'une commune pour un objet de votation ; plusieurs observations d'un même
objet partagent le contexte de cette votation.

**Part de oui communale** :
Nombre de oui divisé par la somme des oui et des non d'une commune pour un objet.

**Historique communal** :
Synthèse des résultats d'objets strictement antérieurs pour une commune, excluant
les objets soumis au vote le même jour que l'objet étudié.

**Bloc de variables** :
Ensemble de caractéristiques regroupées par origine ou sens : historique,
démographie, partis, typologies territoriales ou caractéristiques de l'objet.

**Démonstration rétrospective** :
Analyse de votations passées utilisant des données dont la disponibilité à
l'époque de la prévision n'est pas entièrement établie.
_Avoid_ : Prévision opérationnelle pour qualifier cette démonstration.

**Prévision opérationnelle** :
Prédiction d'un résultat futur utilisant des informations dont la disponibilité
avant l'instant de prévision est établie.

**Test réservé** :
Ensemble de votations tenu à l'écart de l'exploration, du choix des variables et
des réglages, destiné à une évaluation finale indépendante.
