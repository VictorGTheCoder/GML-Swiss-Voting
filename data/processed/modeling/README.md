# Table structurée exploratoire commune × objet

**Analyse rétrospective sur la géographie 2026. Cette table n'est pas validée pour
une prévision historique stricte.** Les sources restent séparées dans leurs dossiers.

## Fichiers

- `municipal_structured.parquet` : une ligne par `municipality_id` × `vote_id` ;
  `yes_share` est la cible, entre 0 et 1.
- `manifest.json` : sélection explicite des prédicteurs, hypothèses temporelles,
  exclusions, couverture, valeurs manquantes et empreintes des sources.
- `feature_dictionary.csv` : rôle, source, type et limite temporelle de chaque colonne.

Reconstruction explicite, après le pipeline des sources :

```bash
python -m scripts.integration.build_modeling_dataset
```

`--start YYYY-MM-DD` change le début de la période cible (2012-01-01 par défaut).
Les observations historiques antérieures sont conservées pour calculer l'historique.
Cette étape n'est pas déclenchée automatiquement par `scripts.run_pipeline --all`.

## Sélection et jointures

- Exclusion des unités spéciales, questions subsidiaires, résultats provisoires et
  anomalies de comptage signalées. Les exclusions sont comptées séquentiellement.
- Historique communal : moyenne non pondérée des objets des dates strictement
  antérieures. Aucun objet du même jour n'entre dans l'historique. Pas de valeur
  de remplacement en l'absence d'historique. Les publications anciennes restent non vérifiées.
- STATPOP : dernière observation dont `available_from` est au plus tard la veille
  du scrutin ; règle conservatrice du 2 septembre Y+1.
- Élections : dernière année d'élection strictement antérieure à l'année du vote.
  `election_selection_from` est un seuil supposé au 1er janvier Y+1, **pas une date
  de publication officielle**. Les neuf partis sont transformés en colonnes.
  PDC, PBD et Centre restent séparés ; les valeurs absentes ne sont pas des zéros.
- Typologies : région linguistique et urbain/rural du snapshot communal 2026,
  sans prétendre qu'ils étaient disponibles à chaque date historique.
- Swissvotes : forme juridique et trois codes de domaines. Jointure exacte par
  `vote_key`, avec contrôle des dates et du type de question. Il s'agit des codes
  de l'édition actuelle ; leurs versions historiques ne sont pas établies.
- Les brochures, résultats du scrutin, participation, recommandations, financement
  et données de campagne ne sont pas ajoutés comme prédicteurs.

## Utilisation

Le périmètre et les comptages effectifs sont dans `manifest.json`. Le rapport
détaillé est généré dans `reports/generated/modeling_dataset/report.md`, avec
une couverture par date dans `coverage_by_date.csv`.

Les colonnes prédictives sont uniquement celles listées dans le manifeste.
Les identifiants, dates, seuils de sélection, cible et indicateurs de protocole ne
doivent pas être utilisés automatiquement comme prédicteurs. Aucune imputation,
normalisation ou sélection fondée sur les scores n'a été effectuée.

Avant de mesurer les performances, fixer des partitions chronologiques par date,
recalculer l'historique selon le protocole retenu (figé ou roulant) et ajuster les
prétraitements uniquement sur l'entraînement. Ne pas transmettre directement cette
table à `scripts.modeling.evaluate_votes`, qui exige des dates de prévision et
des preuves de publication actuellement absentes.
