"""Réglages de la décision : ``config/criteres.yaml`` et ``config/decision.yaml``."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.chemins import Chemins
from src.lecture_yaml import lire_modele

Sens = Literal["hausse", "baisse", "filtre"]


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Critere(_Strict):
    """Entrée du catalogue des critères (section 9)."""

    libelle: str
    axe: str
    unite: str
    sens: Sens
    niveaux: list[Literal["G", "S"]] = Field(min_length=1)
    priorite: Literal["P1"]
    actif_defaut: bool
    actif_si: list[str] = []
    calcul: str | None = None


class CatalogueCriteres(_Strict):
    """Contenu de ``config/criteres.yaml``."""

    axes: dict[str, str] = Field(min_length=1)
    criteres: dict[str, Critere] = Field(min_length=1)


class ParametresDecision(_Strict):
    """Identifiants des paramètres de la section 14."""

    methode: str
    concentration: str
    seuil_robustesse: str
    seuil_correlation: str
    cr_maximal: str
    tirages: str
    graine: str
    capacite: str
    prix_plafond: str
    prix_biochar: str
    prix_credit: str
    part_maximale: str
    cendres_maximales: str
    humidite_maximale: str
    lambda_carbone: str
    sites: str
    rayon_e1: str


class Sensibilite(_Strict):
    """Bornes et pas de l'analyse « un poids à la fois »."""

    variation_min: float
    variation_max: float
    pas: float = Field(gt=0)


class CoucheOsm(_Strict):
    """Couche OSM filtrée sur une liste de valeurs d'étiquette."""

    couche_osm: str
    valeurs: list[str] = Field(min_length=1)
    sortie: str


class Spatial(_Strict):
    """Indicateurs spatiaux des sites."""

    routes: CoucheOsm
    zones: CoucheOsm
    crs_metrique: str
    metres_par_km: float = Field(gt=0)


class Population(_Strict):
    """Population rurale du RGPH 2024."""

    source: str
    fichier: str
    motif_rural: str
    colonne_population: str
    annee: int
    sortie: str


class ConfigDecision(_Strict):
    """Contenu de ``config/decision.yaml``."""

    parametres: ParametresDecision
    methodes: dict[str, str] = Field(min_length=1)
    sensibilite: Sensibilite
    minimum_sites: int = Field(gt=0)
    minimum_criteres: int = Field(gt=0)
    pourcentage: float = Field(gt=0)
    rang_tete: int = Field(gt=0)
    indice_aleatoire: dict[int, float] = Field(min_length=1)
    source_indice_aleatoire: str
    spatial: Spatial
    population: Population
    mois: list[str] = Field(min_length=1)
    dossier_cache: str


def charger_catalogue_criteres(chemins: Chemins) -> CatalogueCriteres:
    """Lit et valide ``config/criteres.yaml``."""
    return lire_modele(chemins.config / "criteres.yaml", CatalogueCriteres)


def charger_config_decision(chemins: Chemins) -> ConfigDecision:
    """Lit et valide ``config/decision.yaml``."""
    return lire_modele(chemins.config / "decision.yaml", ConfigDecision)
