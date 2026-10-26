# Bilan des datasets — 26 octobre 2026

Ce bilan remplace, pour l'état courant, les chiffres de l'audit des brochures du
6 octobre. Il décrit les fichiers préparés et l'audit local, pas des performances ML.

| Source préparée | Taille |
|---|---:|
| Résultats OFS communaux | 1 025 903 lignes |
| Swissvotes | 714 objets |
| STATPOP | 33 760 lignes : 2 110 communes × 16 années |
| Typologies | 2 110 communes |
| Élections harmonisées | 213 700 lignes, commune × élection × parti |
| Correspondance des communes 2010 → 2026 | 2 596 lignes |
| Brochures françaises | 146 PDF, 5 217 pages, 419 objets OFS couverts depuis 1978 |

Les jointures par code couvrent les 2 105 communes ordinaires des résultats OFS
dans STATPOP, les typologies et les élections. Les 511 objets OFS ont une
correspondance Swissvotes contrôlée par identifiant, date et type de question.
Aucun doublon de clé n'a été détecté dans les tables préparées.

STATPOP est téléchargé par export PX complet ; les neuf années 2010–2018 déjà
récupérées via l'API ont été comparées cellule par cellule au PX, sans différence.
Les élections sont harmonisées de la géographie de juillet 2023 vers janvier 2026
par somme des suffrages et recalcul des parts, sans moyenne des pourcentages.

L'extraction des brochures compte 4 304 pages natives et 913 pages OCR, sans échec
technique ; 30 pages ne contiennent pas de texte extrait. Les correspondances
précises sections–objets, la sémantique et la disponibilité pré-scrutin restent
non validées. La couverture par date n'est pas une validation de ces liens.

La [table exploratoire dérivée](../../data/processed/modeling/README.md) contient
262 981 lignes, 125 objets, 44 dates et 2 105 communes, du 11 mars 2012 au
28 septembre 2025. Son mode est explicitement rétrospectif : elle ne constitue
pas une preuve de performance prévisionnelle historique.

## Vérification du nettoyage du dépôt

- Suite locale complète : **185 tests réussis**. Le dernier passage émet 126
  avertissements de scikit-learn sur la propagation de configuration aux workers
  joblib dans `test_final_evaluation.py`, sans échec ; ils n'étaient pas présents
  au passage précédent. L'avertissement pandas de l'audit OFS a été corrigé.
- Ruff et `git diff --check` : aucune erreur.
- Cellules de code des trois notebooks exécutées sur les exports locaux.
- Liens Markdown locaux contrôlés : aucune cible manquante.
- Audit des datasets relancé : `PASS_WITH_LIMITATIONS`, aucune erreur structurelle.
- Table exploratoire reconstruite : 262 981 lignes, mêmes dimensions de couverture.

La CI Windows/Linux est configurée pour la suite complète ; son exécution distante
reste à vérifier sur la pull request. Ces contrôles de nettoyage n'ont pas relancé
les téléchargements ni l'OCR complet.

## Reproduction

```bash
python -m scripts.run_pipeline --all
python -m scripts.integration.build_modeling_dataset
python -m scripts.integration.audit_datasets
python -m pytest tests -q
python -m ruff check scripts tests
```

Les détails et empreintes sont régénérés dans
`reports/generated/dataset_compatibility/audit.json` et
`reports/generated/modeling_dataset/report.md`. Le manifeste de la table exploratoire
est versionné dans `data/processed/modeling/manifest.json`. Les sources raw/interim
et les rapports générés restent hors Git.
