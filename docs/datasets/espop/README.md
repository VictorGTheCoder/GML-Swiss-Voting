# ESPOP — sources et reproduction de l'audit

L'[audit du 27 octobre 2026](../../../reports/datasets/espop/audit_1981_2010.md)
répond au [ticket #65](https://github.com/VictorGTheCoder/GML-Swiss-Voting/issues/65).
Il établit la faisabilité d'une extension ; il ne construit pas de table de
modélisation et ne change pas la période principale provisoire 2012–2025.

Une [recherche complémentaire sur les raccordements existants](existing_projects.md)
documente les données RTS, le projet zurichois et les outils de correspondance
historique, avec les contrôles réalisés et les limites de réutilisation.

## Sources à récupérer

- [Bilan démographique communal OFS](https://www.pxweb.bfs.admin.ch/pxweb/fr/px-x-0102020000_201/-/px-x-0102020000_201.px/)
  : stocks, nationalité, sexe et mouvements depuis 1981.
- [Fiche ESPOP, pages 1–2](https://dam-api.bfs.admin.ch/hub/api/dam/assets/32407015/master)
  : méthode, limites de l'âge communal, révisions de 1992 et 2004.
- [Recensements historiques, annexe Excel](https://dam-api.bfs.admin.ch/hub/api/dam/assets/32067221/appendix)
  : onglets `VZ RFP 1980`, `VZ RFP 1990`, `VZ RFP 2000`, et `Explications`.
  Les onglets `Harm` ne sont pas un correctif général rendant la population
  identique à celle d'ESPOP.
- [Méthodologie des recensements](https://www.census1850.bfs.admin.ch/fr/methodologie-donnees.html)
  : univers de population et territoires historiques.
- [STATPOP](https://www.pxweb.bfs.admin.ch/pxweb/fr/px-x-0102010000_101/-/px-x-0102010000_101.px/)
  : stocks à partir de 2010 ; comparer séparément le bilan ESPOP 2010.

## Rejouer les extractions vérifiées

Exécuter depuis la racine du dépôt dans l'environnement du projet. Le programme
ci-dessous télécharge uniquement les trois extractions de contrôle du rapport.
Il conserve les requêtes, les métadonnées et les octets reçus sous `data/raw/`
(hors Git), dans un nouveau dossier ; il refuse de remplacer un audit existant.
Le CSV PXWeb reçu utilise ici l'encodage Windows-1252 et la virgule comme séparateur.

```python
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

url = ('https://www.pxweb.bfs.admin.ch/api/v1/fr/'
       'px-x-0102020000_201/px-x-0102020000_201.px')
dest = Path('data/raw/espop') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
dest.mkdir(parents=True, exist_ok=False)
response = requests.get(url, timeout=60)
response.raise_for_status()
(dest / 'metadata.json').write_bytes(response.content)
variables = response.json()['variables']
places = list(zip(variables[1]['values'], variables[1]['valueTexts']))
communes = [key for key, label in places if label.startswith('......')]
sample_codes = {'0001', '0261', '1630', '1631', '1632', '2275',
                '4505', '4670', '4695', '5002', '5192', '5586'}
sample = [key for key, label in places
          if label.startswith('......') and label[6:10] in sample_codes]
selections = {
    'stocks_all_communes': [['1981', '1990', '2000', '2009', '2010', '2011'],
                            communes, ['0', '1', '2'], ['0'], ['0', '16']],
    'components_sample': [[str(y) for y in range(1981, 2026)], sample,
                          ['0', '1', '2'], ['0'], variables[4]['values']],
    'sex_sample': [['1981', '2009', '2010', '2011'], sample,
                   ['0'], ['0', '1', '2'], ['0', '16']],
}
for name, selection in selections.items():
    query = {'query': [
        {'code': var['code'], 'selection': {'filter': 'item', 'values': values}}
        for var, values in zip(variables, selection)
    ], 'response': {'format': 'csv'}}
    (dest / f'{name}.query.json').write_text(
        json.dumps(query, ensure_ascii=False, indent=2), encoding='utf-8')
    response = requests.post(url, json=query, timeout=60)
    response.raise_for_status()
    (dest / f'{name}.csv').write_bytes(response.content)
print(dest)
```

Les clés géographiques de sélection de l'API sont des positions dans le cube,
**pas** les numéros OFS : les retrouver par les libellés des métadonnées.
Pour analyser les CSV : `pd.read_csv(path, encoding='cp1252', dtype=str)` ;
extraire le numéro avec `r'^\.+(\d+) '` et normaliser les zéros initiaux.
Interpréter les marqueurs non numériques comme manquants, jamais comme zéro.
Une nouvelle version du cube peut changer les chiffres, clés ou dimensions :
conserver son propre instant de collecte et comparer ses empreintes au rapport.

Pour reproduire les contrôles de l'audit : vérifier l'unicité
année × code × nationalité × sexe, la présence des deux stocks, puis
`Total = Suisse + Étranger` pour chaque stock ; comparer les codes aux snapshots
du répertoire communal. Pour les recensements, lire les trois onglets avec
`pd.read_excel(..., header=None)` : lignes de données à partir de l'indice 6,
année/code/nom en colonnes 0/1/2, total en 3, Suisses/étrangers en 4/5, six
classes d'âge en 6–11. Les six classes doivent sommer au total sur les lignes
complètes ; le rapport explicite le cas incomplet de 1980.

## Exports pour une future expérience

Conserver l'export prioritaire proposé : 1981–2010, toutes les entrées communales,
nationalité Total/Suisse/Étranger, sexe Total, stocks de janvier et décembre.
Pour un second export : nationalité et sexe Total ; naissances, décès, solde
migratoire, **ainsi que divergence statistique et variation** pour contrôler le bilan.
Le troisième export par sexe reste facultatif. Ces exports ne sont pas encore
des features admissibles : version, territoire et disponibilité doivent être établis.

Les mouvements supplémentaires restent des candidats pour une expérience
ultérieure. Leur récupération ne les ajoute pas aux 30 features de la V1.
