"""Emplacements des dossiers de l'outil.

La racine est le dossier du dépôt ; la variable d'environnement ``AB_DSS_RACINE`` permet de la
remplacer (par exemple pour travailler sur une copie des données).
"""

import os
from dataclasses import dataclass
from pathlib import Path

VARIABLE_RACINE = "AB_DSS_RACINE"


@dataclass(frozen=True)
class Chemins:
    """Dossiers utilisés par l'outil, tous dérivés de la racine."""

    racine: Path

    @property
    def config(self) -> Path:
        """Fichiers YAML de configuration (paramètres, entreprise, critères…)."""
        return self.racine / "config"

    @property
    def donnees(self) -> Path:
        """Dossier des données."""
        return self.racine / "data"

    @property
    def brutes(self) -> Path:
        """Fichiers téléchargés, jamais modifiés (RG-01)."""
        return self.donnees / "raw"

    @property
    def manuelles(self) -> Path:
        """Fichiers saisis à la main par l'équipe (``<source>/``), versionnés dans Git.

        Ils sont lus sans être modifiés, comme ``data/raw/`` (RG-01) ; les documents qu'ils
        citent (pages archivées, cartes) restent dans ``data/raw/``, hors de Git.
        """
        return self.donnees / "manuelles"

    @property
    def saisies(self) -> Path:
        """Tables de référence saisies (CSV)."""
        return self.donnees / "input"

    @property
    def preparees(self) -> Path:
        """Tables préparées par ``scripts.prepare`` (Parquet, GeoPackage)."""
        return self.donnees / "processed"

    @property
    def versions(self) -> Path:
        """Copies des tables pour chaque version (RG-17)."""
        return self.donnees / "versions"

    @property
    def scenarios(self) -> Path:
        """Scénarios enregistrés (YAML)."""
        return self.racine / "scenarios"


def chemins_par_defaut() -> Chemins:
    """Renvoie les chemins de l'outil, à partir de ``AB_DSS_RACINE`` ou du dépôt."""
    racine = os.environ.get(VARIABLE_RACINE)
    if racine:
        return Chemins(Path(racine).resolve())
    return Chemins(Path(__file__).resolve().parents[1])


def donnees_preparees(chemins: Chemins) -> bool:
    """Indique si ``scripts.prepare`` a déjà produit au moins une table."""
    dossier = chemins.preparees
    if not dossier.is_dir():
        return False
    return any(f.suffix in {".parquet", ".gpkg"} for f in dossier.iterdir())
