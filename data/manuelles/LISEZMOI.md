# data/manuelles · Tables saisies à la main par l'équipe

Ce dossier contient les tables (CSV) saisies par l'équipe à partir de documents consultés à la
main. Contrairement à `data/raw/`, il est versionné dans Git : une installation neuve les a
d'emblée, sans dépôt manuel.

Comme `data/raw/`, ces fichiers ne sont jamais modifiés par l'outil (RG-01). Une correction se
fait en déposant une nouvelle version du fichier, puis en relançant `python -m scripts.prepare`.

- `SRC-18/` : communiqués des DRA et DPA (production et superficie par province).
  `references.csv`, `valeurs_saisies.csv` et `valeurs_verifiees.csv`, lus par
  `python -m scripts.prepare`.
- `SRC-08/` : valeurs de la littérature saisies pour les résidus (`litterature_residus.csv`) et
  leur vérification ligne par ligne (`valeurs_verifiees.csv`). Trace de la saisie : les valeurs
  retenues sont dans `data/input/residus.csv` et `data/input/concurrence.csv`.

Les documents cités (pages web archivées, PDF) restent dans `data/raw/<source>/`, hors de Git ;
`python -m scripts.download` inscrit les fichiers des deux dossiers dans `data/sources.yaml`
(taille et empreinte SHA-256, RG-05). Format des colonnes :
[docs/donnees_manuelles.md](../../docs/donnees_manuelles.md).
