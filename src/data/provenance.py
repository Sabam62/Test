"""Provenance des valeurs (RG-03), source obligatoire (RG-18) et marqueur « À compléter » (RG-14).

Une :class:`ValeurSourcee` est une valeur accompagnée de son unité, de sa :class:`Provenance`
(source, année, statut, version) et, si la source donne une fourchette, de sa loi d'incertitude :

- fourchette sans mode : loi uniforme (min, max), valeur centrale = milieu de la fourchette,
  statut « Hypothèse » (décision du 22/11/2026) ;
- fourchette avec un mode donné par la source : loi triangulaire (min, mode, max), valeur = mode.

« À compléter » n'est pas un statut : c'est l'absence de valeur. La lire lève
:class:`ValeurACompleter`, qui bloque le seul calcul concerné et dit où trouver la valeur.

Les champs de provenance peuvent être donnés « à plat » (``source_id``, ``annee``, ``statut``…),
comme dans les colonnes des tables au format long ; ils sont regroupés dans ``provenance``.
"""

import math
import statistics
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

A_COMPLETER = "À compléter"


class Statut(StrEnum):
    """Statut d'une valeur (section 3 du cahier des charges)."""

    MESUREE = "Mesurée"
    ESTIMEE = "Estimée"
    LITTERATURE = "Littérature"
    TERRAIN = "Terrain"
    HYPOTHESE = "Hypothèse"


class Loi(StrEnum):
    """Loi d'incertitude utilisée par le Monte Carlo."""

    UNIFORME = "uniforme"
    TRIANGULAIRE = "triangulaire"


class ValeurACompleter(Exception):
    """Un calcul a lu une valeur « À compléter » (RG-14)."""

    def __init__(self, nom: str, ou_trouver: str) -> None:
        """Construit le message qui nomme la valeur manquante et dit où la trouver."""
        self.nom = nom
        self.ou_trouver = ou_trouver
        super().__init__(
            f"La valeur « {nom} » est à compléter (RG-14) : le calcul qui en dépend est bloqué. "
            f"Où la trouver : {ou_trouver}."
        )


class Provenance(BaseModel):
    """Origine d'une valeur : source du manifeste, année, statut et version des données."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(min_length=1, description="Identifiant dans data/sources.yaml")
    annee: int | None = Field(default=None, description="Année de la valeur ; None = à compléter")
    statut: Statut
    version: str | None = Field(
        default=None,
        description="Version des données qui a introduit la valeur ; None = valeur livrée",
    )
    autres_sources: tuple[str, ...] = Field(
        default=(), description="Sources citées ensemble, sans attribution valeur par valeur"
    )
    note: str | None = None


CHAMPS_PROVENANCE = frozenset(Provenance.model_fields)


class ValeurSourcee(BaseModel):
    """Valeur, unité, provenance et loi d'incertitude éventuelle."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    nom: str = Field(min_length=1, description="Désignation affichée dans les messages")
    valeur: float | str | None = Field(description="Nombre, choix textuel, ou None = à compléter")
    unite: str = Field(min_length=1)
    provenance: Provenance | None = None
    ou_trouver: str | None = Field(default=None, description="Où trouver une valeur à compléter")
    statut_attendu: Statut | None = Field(
        default=None, description="Statut qu'aura une valeur à compléter une fois saisie"
    )
    min: float | None = None
    mode: float | None = None
    max: float | None = None
    loi: Loi | None = None

    @model_validator(mode="before")
    @classmethod
    def _regrouper_provenance(cls, donnees: object) -> object:
        if not isinstance(donnees, dict):
            return donnees
        donnees = dict(donnees)
        nom = donnees.get("nom", "valeur")
        if donnees.get("valeur") == A_COMPLETER:
            donnees["valeur"] = None
        a_plat = {k: donnees.pop(k) for k in list(donnees) if k in CHAMPS_PROVENANCE}
        if donnees.get("valeur") is None and "source_id" not in a_plat:
            # Valeur à compléter : le statut annoncé est celui de la future saisie.
            if "statut" in a_plat:
                donnees["statut_attendu"] = a_plat.pop("statut")
            if a_plat:
                raise ValueError(
                    f"« {nom} » est à compléter : seuls statut et ou_trouver sont admis, "
                    f"pas {', '.join(sorted(a_plat))}."
                )
        if a_plat and "provenance" in donnees:
            raise ValueError(f"« {nom} » : provenance donnée deux fois.")
        provenance = donnees.get("provenance", a_plat or None)
        if donnees.get("valeur") is not None:
            if not isinstance(provenance, dict | Provenance):
                raise ValueError(f"« {nom} » : source obligatoire (RG-18).")
            if isinstance(provenance, dict):
                if not str(provenance.get("source_id") or "").strip():
                    raise ValueError(f"« {nom} » : source obligatoire (RG-18), indiquez source_id.")
                if not provenance.get("statut"):
                    raise ValueError(f"« {nom} » : statut obligatoire (RG-18), indiquez statut.")
        if provenance is not None:
            donnees["provenance"] = provenance
        return donnees

    @model_validator(mode="after")
    def _verifier(self) -> Self:
        bornes = (self.min, self.mode, self.max, self.loi)
        a_une_fourchette = any(b is not None for b in bornes)
        if self.valeur is None:
            if not self.ou_trouver:
                raise ValueError(f"« {self.nom} » est à compléter : indiquez où trouver la valeur.")
            if a_une_fourchette:
                raise ValueError(
                    f"« {self.nom} » est à compléter : retirez la fourchette et la loi."
                )
            return self
        if self.statut_attendu is not None:
            raise ValueError(
                f"« {self.nom} » a une valeur : son statut va dans la provenance, "
                "pas dans statut_attendu."
            )
        if isinstance(self.valeur, str):
            if a_une_fourchette:
                raise ValueError(f"« {self.nom} » est un choix textuel : ni fourchette ni loi.")
            return self
        if not a_une_fourchette:
            return self
        return self._verifier_loi()

    def _verifier_loi(self) -> Self:
        valeur = self.lire_nombre()
        if self.loi is None:
            raise ValueError(
                f"« {self.nom} » : une fourchette demande une loi (uniforme ou triangulaire)."
            )
        if self.min is None or self.max is None:
            raise ValueError(f"« {self.nom} » : la loi {self.loi} demande min et max.")
        if not self.min <= valeur <= self.max:
            raise ValueError(
                f"« {self.nom} » : la valeur {valeur} sort de sa fourchette "
                f"[{self.min} ; {self.max}]."
            )
        if self.loi is Loi.UNIFORME:
            self._verifier_uniforme(valeur, self.min, self.max)
        else:
            self._verifier_triangulaire(valeur, self.min, self.max)
        return self

    def _verifier_uniforme(self, valeur: float, bas: float, haut: float) -> None:
        if self.mode is not None:
            raise ValueError(
                f"« {self.nom} » : la loi uniforme n'a pas de mode ; si la source en donne un, "
                "choisissez la loi triangulaire."
            )
        milieu = statistics.fmean((bas, haut))
        if not math.isclose(valeur, milieu):
            raise ValueError(
                f"« {self.nom} » : avec une loi uniforme, la valeur est le milieu de la fourchette "
                f"({milieu})."
            )
        if self.provenance is None or self.provenance.statut is not Statut.HYPOTHESE:
            raise ValueError(
                f"« {self.nom} » : le milieu d'une fourchette porte le statut « Hypothèse »."
            )

    def _verifier_triangulaire(self, valeur: float, bas: float, haut: float) -> None:
        if self.mode is None:
            raise ValueError(
                f"« {self.nom} » : la loi triangulaire demande le mode donné par la source ; "
                "sans mode, choisissez la loi uniforme."
            )
        if not bas <= self.mode <= haut:
            raise ValueError(f"« {self.nom} » : le mode {self.mode} sort de sa fourchette.")
        if not math.isclose(valeur, self.mode):
            raise ValueError(
                f"« {self.nom} » : avec une loi triangulaire, la valeur est le mode ({self.mode})."
            )

    @property
    def est_a_completer(self) -> bool:
        """Vrai si la valeur manque (RG-14)."""
        return self.valeur is None

    def lire(self) -> float | str:
        """Renvoie la valeur ; lève :class:`ValeurACompleter` si elle manque (RG-14)."""
        if self.valeur is None:
            raise ValeurACompleter(self.nom, self.ou_trouver or "")
        return self.valeur

    def lire_nombre(self) -> float:
        """Renvoie la valeur numérique ; lève une erreur si elle manque ou si c'est un texte."""
        valeur = self.lire()
        if isinstance(valeur, str):
            raise TypeError(f"« {self.nom} » vaut « {valeur} », qui n'est pas un nombre.")
        return valeur
