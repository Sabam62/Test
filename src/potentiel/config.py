"""Réglages du calcul des gisements : ``config/potentiel.yaml`` (section 8.1)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.chemins import Chemins
from src.data.provenance import Statut
from src.lecture_yaml import lire_modele

FICHIER_CONFIG = "potentiel.yaml"
Role = Literal["culture", "variante", "region", "secours", "etat", "information"]


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class UniteRatio(_Strict):
    """Unité d'un ratio : base (δ_r = 1 en masse brute, 0 en matière sèche) et facteur vers t."""

    base: Literal["MS", "brute"]
    facteur_tonne: float = Field(gt=0)


class RolePrecision(_Strict):
    """Rôle d'une précision de ``residus.csv`` pour un résidu et un paramètre."""

    residu: str
    parametre: str
    role: Role
    choix_par: str | None = None

    @model_validator(mode="after")
    def _choix(self) -> "RolePrecision":
        if (self.role == "variante") != (self.choix_par is not None):
            raise ValueError(
                f"{self.residu} · {self.parametre} : « choix_par » est exigé pour une variante, "
                "et seulement pour elle."
            )
        return self


class Indicateur(_Strict):
    """Indicateur des gisements : libellé, unité, somme nationale possible."""

    libelle: str = Field(min_length=1)
    unite: str = Field(min_length=1)
    additif: bool


class ConfigPotentiel(_Strict):
    """Contenu de ``config/potentiel.yaml``."""

    parametre_campagnes: str
    unites_ratio: dict[str, UniteRatio] = Field(min_length=1)
    unites_fraction: dict[str, float] = Field(min_length=1)
    unite_densite: str
    grandeurs_par_mode: dict[str, str] = Field(min_length=1)
    multiplicateurs: dict[str, list[str]] = {}
    precisions: list[RolePrecision] = []
    ordre_statuts: list[Statut] = Field(min_length=1)
    hectares_par_km2: float = Field(gt=0)
    indicateurs: dict[str, Indicateur] = Field(min_length=1)
    statut_u_national: Statut

    @model_validator(mode="after")
    def _statuts_complets(self) -> "ConfigPotentiel":
        manquants = [s.value for s in Statut if s not in self.ordre_statuts]
        if manquants or len(set(self.ordre_statuts)) != len(self.ordre_statuts):
            raise ValueError(
                f"ordre_statuts doit citer chaque statut une fois (manquants : {manquants})."
            )
        return self

    def role(self, residu: str, parametre: str) -> RolePrecision | None:
        """Rôle des précisions d'un paramètre d'un résidu ; None si aucune n'est déclarée."""
        return next(
            (p for p in self.precisions if (p.residu, p.parametre) == (residu, parametre)), None
        )

    def moins_fiable(self, statuts: list[Statut]) -> Statut:
        """Statut le moins fiable d'une liste (statut d'une valeur calculée)."""
        return min(statuts, key=self.ordre_statuts.index)


def charger_config_potentiel(chemins: Chemins) -> ConfigPotentiel:
    """Lit et valide ``config/potentiel.yaml``."""
    return lire_modele(chemins.config / FICHIER_CONFIG, ConfigPotentiel)
