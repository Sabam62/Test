"""Réglages de la préparation des données : ``config/preparation.yaml``."""

from pydantic import BaseModel, ConfigDict, Field

from src.chemins import Chemins
from src.lecture_yaml import lire_modele

FICHIER_CONFIG = "preparation.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ConfigSurfaces(_Strict):
    """Section ``cropgrids`` : surfaces CROPGRIDS par province."""

    variable: str = Field(min_length=1)
    crs: str = Field(min_length=1)
    annee: int
    fraction_minimale: float = Field(ge=0)
    sortie: str = Field(min_length=1)
    sortie_agricole: str = Field(min_length=1)


class ConfigSrc18(_Strict):
    """Section ``src18`` : valeurs saisies et vérifiées des communiqués DRA et DPA."""

    dossier: str = Field(min_length=1)
    saisies: str = Field(min_length=1)
    verifiees: str = Field(min_length=1)
    references: str = Field(min_length=1)
    verification_valide: str = Field(min_length=1)
    variables: dict[str, str] = Field(min_length=1)
    unites: dict[str, str] = Field(min_length=1)
    non_utilisees: dict[str, str]
    periodes_avec_campagne: list[str] = Field(min_length=1)
    periodes_sans_campagne: dict[str, str]


class ColonnesSrc01(_Strict):
    """Noms des colonnes du fichier SRC-01."""

    campagne: str
    filiere: str
    produit: str
    indicateur: str
    valeur: str


class ConfigSrc01(_Strict):
    """Section ``src01`` : Production végétale 2010-2022 (total national)."""

    dossier: str = Field(min_length=1)
    fichier: str = Field(min_length=1)
    colonnes: ColonnesSrc01
    separateur_campagne: str = Field(min_length=1)
    indicateurs: dict[str, str] = Field(min_length=1)
    produits: dict[str, list[str]] = Field(min_length=1)


class ConfigSorties(_Strict):
    """Noms des fichiers écrits dans ``data/processed/``."""

    observations: str = Field(min_length=1)
    production: str = Field(min_length=1)
    rapport: str = Field(min_length=1)


class ConfigPreparation(_Strict):
    """Contenu de ``config/preparation.yaml``."""

    cropgrids: ConfigSurfaces
    src18: ConfigSrc18
    src01: ConfigSrc01
    sorties: ConfigSorties


def charger_config_preparation(chemins: Chemins) -> ConfigPreparation:
    """Lit et valide ``config/preparation.yaml``."""
    return lire_modele(chemins.config / FICHIER_CONFIG, ConfigPreparation)
