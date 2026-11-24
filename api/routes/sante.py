"""Route de santé : l'interface l'interroge au démarrage."""

from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter
from pydantic import BaseModel

from src.chemins import chemins_par_defaut, donnees_preparees
from src.lecture_yaml import ErreurConfiguration
from src.logistique.config import charger_config_logistique
from src.logistique.distances import osrm_disponible

routeur = APIRouter(tags=["santé"])
OSRM_ACTIF = "actif"
OSRM_ARRETE = "arrêté : distances à vol d'oiseau × détour"


def _etat_osrm() -> str:
    """État du routage local, affiché dans le contexte du scénario (section 12.1)."""
    try:
        config = charger_config_logistique(chemins_par_defaut())
    except ErreurConfiguration:
        return OSRM_ARRETE
    return OSRM_ACTIF if osrm_disponible(config) else OSRM_ARRETE


class Sante(BaseModel):
    """État de l'outil."""

    statut: str
    version_outil: str
    donnees_preparees: bool
    osrm: str


def _version_outil() -> str:
    try:
        return version("ab-dss")
    except PackageNotFoundError:
        return "non installée"


@routeur.get("/sante")
def sante() -> Sante:
    """Indique que l'API répond et si les données ont été préparées."""
    return Sante(
        statut="ok",
        version_outil=_version_outil(),
        donnees_preparees=donnees_preparees(chemins_par_defaut()),
        osrm=_etat_osrm(),
    )
