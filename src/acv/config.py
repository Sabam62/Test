"""Réglages de l'ACV : ``config/acv.yaml`` (section 8.3)."""

from pydantic import BaseModel, ConfigDict, Field

from src.chemins import Chemins
from src.lecture_yaml import lire_modele

FICHIER_CONFIG = "acv.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Flux(_Strict):
    """Flux élémentaire de la biosphère et composante de PAR-27 qui le caractérise."""

    nom: str
    compartiment: list[str] = Field(min_length=1)
    prg: str


class ArrierePlan(_Strict):
    """Activité agrégée : unité de référence et échanges (paramètre → flux)."""

    unite: str
    echanges: dict[str, str] = Field(min_length=1)
    multiplicateurs: list[str] = []
    facteur: float = Field(default=1, gt=0)


class ParametresAcv(_Strict):
    """Identifiants des paramètres de la section 14."""

    temperature: str
    permanence: str
    consommation_camion: str
    charge_camion: str
    volume_camion: str


class ConfigAcv(_Strict):
    """Contenu de ``config/acv.yaml``."""

    projet: str
    base_avant_plan: str
    base_biosphere: str
    methode: list[str] = Field(min_length=1)
    unite_methode: str
    flux: dict[str, Flux] = Field(min_length=1)
    arriere_plan: dict[str, ArrierePlan] = Field(min_length=1)
    activites: dict[str, list[str]]
    parametres: ParametresAcv
    classes_temperature: dict[str, float] = Field(min_length=1)
    source_classes: str
    precisions_carbone_biochar: dict[str, str] = {}
    masse_molaire_co2: float = Field(gt=0)
    masse_molaire_c: float = Field(gt=0)
    kg_par_tonne: float = Field(gt=0)
    litres_par_100_km: float = Field(gt=0)
    trajets_par_rotation: float = Field(gt=0)
    scenarios_reference: dict[str, str | None] = Field(min_length=1)  # None : E_ref = 0
    etapes: dict[str, str] = Field(min_length=1)
    standard_par_defaut: str
    unite_fonctionnelle: str


def charger_config_acv(chemins: Chemins) -> ConfigAcv:
    """Lit et valide ``config/acv.yaml``."""
    return lire_modele(chemins.config / FICHIER_CONFIG, ConfigAcv)
