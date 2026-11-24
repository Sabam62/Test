"""Réglages de la logistique : ``config/logistique.yaml`` (section 8.2)."""

from pydantic import BaseModel, ConfigDict, Field

from src.chemins import Chemins
from src.lecture_yaml import lire_modele

FICHIER_CONFIG = "logistique.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ConfigRattachement(_Strict):
    """Points de rattachement des gisements (H1)."""

    variable_cropgrids: str
    sortie: str


class ConfigSites(_Strict):
    """Sources des sites candidats."""

    source_osm: str
    fichier_osm: str
    couche_osm: str
    types_lieux: list[str] = Field(min_length=1)
    sortie_chefs_lieux: str
    fichier_agropoles: str
    fichier_chefs_lieux: str
    fichier_utilisateur: str


class ConfigOsrm(_Strict):
    """Service de routage local (SRC-07)."""

    url: str
    profil: str
    delai_secondes: float = Field(gt=0)
    delai_test_secondes: float = Field(gt=0)
    lot: int = Field(gt=0)


class ParametresLogistique(_Strict):
    """Identifiants des paramètres de la section 14 utilisés par le coût livré."""

    capacite: str
    prix_plafond: str
    distance_maximale: str
    prix_gazole: str
    consommation: str
    part_carburant: str
    charge_maximale: str
    volume_utile: str
    cout_fixe: str
    rayon_c3: str


class ParametresResidus(_Strict):
    """Paramètres de ``residus.csv`` utilisés."""

    humidite: str
    densite_apparente: str
    cout_collecte: str
    cout_pretraitement: str


class ParametresConcurrence(_Strict):
    """Paramètres de ``concurrence.csv`` utilisés."""

    prix_achat: str
    unite_prix: str


class ConfigLogistique(_Strict):
    """Contenu de ``config/logistique.yaml``."""

    rattachement: ConfigRattachement
    sites: ConfigSites
    osrm: ConfigOsrm
    parametre_detour: str
    rayon_terre_km: float = Field(gt=0)
    metres_par_km: float = Field(gt=0)
    secondes_par_minute: float = Field(gt=0)
    dossier_cache: str
    trajets_par_rotation: float = Field(gt=0)
    parametres: ParametresLogistique
    conversions: dict[str, float]
    residus: ParametresResidus
    concurrence: ParametresConcurrence
    indicateur_gisement: str


def charger_config_logistique(chemins: Chemins) -> ConfigLogistique:
    """Lit et valide ``config/logistique.yaml``."""
    return lire_modele(chemins.config / FICHIER_CONFIG, ConfigLogistique)
