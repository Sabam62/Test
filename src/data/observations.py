"""Observations statistiques lues dans les sources, et bilan des contrôles (UC-DAT-02).

Une observation est une valeur publiée (production ou superficie) pour une zone (province ou
groupe de provinces, région, pays), une culture et une campagne, avec sa provenance (RG-03).
Toutes les sources sont ramenées à ce format long avant la désagrégation (RG-04).

Le bilan des contrôles classe chaque ligne lue, par source, en : valide, rejetée, doublon,
aberrante (signalée, conservée) ou non utilisée (valide mais hors du calcul, avec le motif).
"""

import re
from dataclasses import dataclass, field
from enum import StrEnum

import pandas as pd

NATIONAL = "NATIONAL"
SEPARATEUR_CODES = ";"
COLONNES_OBSERVATIONS = [
    "source_id",
    "document",
    "url",
    "organisme",
    "ligne",
    "niveau",
    "code_zone",
    "codes_provinces",
    "code_culture",
    "campagne",
    "periode",
    "variable",
    "valeur",
    "unite",
    "previsionnel",
    "statut",
    "annee",
    "version",
    "methode",
    "note",
]
_CAMPAGNE = re.compile(r"^(\d{4})-(\d{4})$")


class ErreurPreparation(Exception):
    """Préparation impossible (fichier manquant, colonne absente…) ; message en français."""


class Niveau(StrEnum):
    """Maille d'une observation."""

    PROVINCE = "province"
    REGION = "region"
    NATIONAL = "national"


class Categorie(StrEnum):
    """Classement d'une ligne lue (rapport de contrôle, UC-DAT-02)."""

    VALIDE = "valide"
    REJETEE = "rejetée"
    DOUBLON = "doublon"
    ABERRANTE = "aberrante"
    NON_UTILISEE = "non utilisée"


@dataclass(frozen=True)
class Signalement:
    """Une ligne d'une source et son classement."""

    source_id: str
    fichier: str
    ligne: int
    categorie: Categorie
    motif: str


@dataclass
class BilanControle:
    """Lignes lues et classées, par source."""

    signalements: list[Signalement] = field(default_factory=list)
    lues: dict[tuple[str, str], int] = field(default_factory=dict)

    def lire(self, source_id: str, fichier: str, nombre: int) -> None:
        """Enregistre le nombre de lignes lues dans un fichier."""
        self.lues[(source_id, fichier)] = self.lues.get((source_id, fichier), 0) + nombre

    def signaler(
        self, source_id: str, fichier: str, ligne: int, categorie: Categorie, motif: str
    ) -> None:
        """Classe une ligne."""
        self.signalements.append(Signalement(source_id, fichier, ligne, categorie, motif))

    def compter(self, categorie: Categorie, source_id: str | None = None) -> int:
        """Nombre de lignes d'une catégorie (toutes sources, ou une seule)."""
        return sum(
            1
            for s in self.signalements
            if s.categorie is categorie and source_id in (None, s.source_id)
        )

    def tableau(self) -> pd.DataFrame:
        """Signalements en tableau (une ligne par signalement)."""
        return pd.DataFrame(
            [s.__dict__ for s in self.signalements],
            columns=["source_id", "fichier", "ligne", "categorie", "motif"],
        )


def campagne_valide(texte: str) -> bool:
    """Vrai pour une campagne « 2017-2018 » (deux années consécutives)."""
    trouve = _CAMPAGNE.match(texte)
    if not trouve:
        return False
    debut, fin = (int(x) for x in trouve.groups())
    return fin - debut == 1


def annee_campagne(campagne: str) -> int:
    """Année de provenance d'une campagne : son année de fin (« 2017-2018 » → 2018)."""
    return int(campagne.split("-")[-1])


def campagne_precedente(campagne: str) -> str:
    """« 2018-2019 » → « 2017-2018 »."""
    debut, fin = (int(x) for x in campagne.split("-"))
    return f"{debut - 1}-{fin - 1}"


def tableau_observations(lignes: list[dict[str, object]]) -> pd.DataFrame:
    """Observations au format long, colonnes dans l'ordre de :data:`COLONNES_OBSERVATIONS`."""
    table = pd.DataFrame(lignes, columns=COLONNES_OBSERVATIONS)
    table["valeur"] = table["valeur"].astype(float)
    table["previsionnel"] = table["previsionnel"].astype(bool)
    table["annee"] = table["annee"].astype("Int64")
    return table
