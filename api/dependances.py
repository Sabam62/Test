"""Dépendances des routes : dossiers de l'outil, référentiel, réglages de l'API.

Pendant une démonstration (:mod:`src.scenarios.demo`), ``obtenir_chemins`` renvoie la copie de
travail : les calculs, les saisies et les exports n'atteignent jamais les dossiers réels.

Les tests remplacent ``obtenir_chemins`` et ``obtenir_referentiel`` (``dependency_overrides``)
pour travailler sur une copie de l'extrait figé des données réelles.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from pydantic import BaseModel, ConfigDict, Field

from src.chemins import Chemins, chemins_par_defaut
from src.data.provinces import Referentiel, charger_referentiel
from src.lecture_yaml import lire_modele
from src.scenarios.demo import chemins_de_travail

FICHIER_CONFIG = "api.yaml"


class ConfigApi(BaseModel):
    """Contenu de ``config/api.yaml``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    simplification_geojson_degres: float = Field(ge=0)
    attribution_cartes: str = Field(min_length=1)
    lignes_par_page: int = Field(gt=0)
    classes_carte: int = Field(gt=1)


def obtenir_chemins_reels() -> Chemins:
    """Dossiers de l'utilisateur (racine du dépôt ou ``AB_DSS_RACINE``)."""
    return chemins_par_defaut()


def obtenir_chemins(reel: Annotated[Chemins, Depends(obtenir_chemins_reels)]) -> Chemins:
    """Dossiers de calcul : la copie de travail si une démonstration est chargée, sinon le réel."""
    return chemins_de_travail(reel)


@lru_cache(maxsize=1)
def _referentiel(racine: Path) -> Referentiel:
    return charger_referentiel(Chemins(racine))


def obtenir_referentiel(chemins: Annotated[Chemins, Depends(obtenir_chemins)]) -> Referentiel:
    """Référentiel des provinces (RG-02), lu une fois par lancement."""
    return _referentiel(chemins.racine)


def charger_config_api(chemins: Chemins) -> ConfigApi:
    """Lit et valide ``config/api.yaml``."""
    return lire_modele(chemins.config / FICHIER_CONFIG, ConfigApi)
