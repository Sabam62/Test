# data/raw · Fichiers bruts des sources

Ce dossier contient les fichiers des sources, tels qu'ils ont été téléchargés ou déposés.
Ils ne sont jamais modifiés (RG-01) : tout traitement écrit dans `data/processed/`.
Ils ne sont pas versionnés dans Git (certains pèsent plusieurs centaines de Mo).

- Un sous-dossier par source : `data/raw/SRC-05/`, `data/raw/SRC-18/`…
- Les tables saisies à la main par l'équipe (CSV des communiqués SRC-18, littérature SRC-08) ne
  sont pas ici mais dans [data/manuelles/](../manuelles/LISEZMOI.md), versionné dans Git.
- `python -m scripts.download` récupère les sources à adresse stable (SRC-01, 04, 05, 06, 09),
  sans jamais réécrire un fichier présent, et inscrit chaque fichier dans `data/sources.yaml`
  (adresse, date, taille, empreinte SHA-256, RG-05).
- Les autres fichiers se déposent à la main : nom de fichier et dossier attendus dans
  [docs/donnees_manuelles.md](../../docs/donnees_manuelles.md). Relancer ensuite
  `python -m scripts.download` inscrit leur empreinte dans le manifeste.
