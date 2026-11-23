# Métadonnées OFS vérifiées le 23 novembre 2026

Capture effectuée le **23 novembre 2026 à 12:32:01 UTC**, depuis le
[téléchargement officiel du cube PX](https://www.pxweb.bfs.admin.ch/DownloadFile.aspx?file=px-x-1703030000_101)
`px-x-1703030000_101`, consacré aux votations fédérales par commune.

## Contenu et preuve

- `header.px-header.txt` conserve l'en-tête original, arrêté avant la section
  `DATA`. Il contient les métadonnées, les identifiants et les libellés de
  dimensions ; aucune valeur de résultat n'a été extraite ou enregistrée.
- `metadata.json` conserve l'heure de récupération, les URL, des en-têtes HTTP,
  les métadonnées utiles, les mois provisoires extraits et l'empreinte de
  l'en-tête.
- Taille de l'en-tête : **247 495 octets**.
- SHA-256 :
  `67c3edef92340c9434b1fc1d8b5b47cd22e87050117998f4f1b10bef4f8e8f39`.

`LAST-UPDATED` vaut `20260821 08:30`. La note française indique un état de base
en août 2026 et contient :

> Résultats provisoires: novembre 2025, mars et juin 2026

Ces mois sont donc toujours déclarés provisoires dans le cube servi au moment
de la capture. Leur exclusion du jeu définitif reste conforme à cette source.
La même note est consultable sur la
[page officielle PXWeb](https://www.pxweb.bfs.admin.ch/pxweb/fr/px-x-1703030000_101/px-x-1703030000_101/px-x-1703030000_101.px/).

## Géographie et limites

Les résultats sont harmonisés sur les **communes au 1er janvier 2026**. La note
précise notamment le transfert de Moutier de Berne au Jura et la présence
d'unités spéciales de la statistique politique. Cette référence géographique
actuelle ne constitue pas une archive des communes telles qu'elles existaient
à chaque scrutin.

La vérification confirme le statut déclaré des mois provisoires. **Les valeurs
du cube actuel et celles du parquet local n'ont pas été comparées** : leur
identité intégrale n'est pas établie. L'empreinte ci-dessus porte sur l'en-tête,
pas sur le fichier PX complet. Aucun fichier `data/processed` n'a été modifié.
