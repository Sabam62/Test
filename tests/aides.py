"""Outils communs des tests : copies de config/ sans les fichiers locaux de l'utilisateur."""

import shutil
from pathlib import Path

# Fichiers locaux ignorés par Git (saisies de l'entreprise, réglages) : jamais copiés dans les
# essais, pour que les tests ne dépendent pas des saisies faites sur le poste.
FICHIERS_LOCAUX = (
    "entreprise.local.yaml",
    "parametres_modifies.yaml",
    "sites.local.yaml",
    "decision.local.yaml",
)


def copier_config(source: Path, cible: Path) -> None:
    """Copie ``config/`` dans ``cible`` sans les fichiers locaux."""
    shutil.copytree(source, cible, ignore=shutil.ignore_patterns(*FICHIERS_LOCAUX))
