"""Manifeste des sources ``data/sources.yaml`` (RG-05) et empreintes des fichiers bruts.

Le manifeste liste les sources SRC-01 à SRC-19 du catalogue (section 7.1), les publications
de la section 14 rattachées à leur source parente, et l'entrée ``CDC`` (décisions et propositions
du cahier des charges). Pour les sources à adresse stable, ``telechargement`` décrit comment
``python -m scripts.download`` les récupère ; ``fichiers`` garde, pour chaque fichier de
``data/raw/<source>/``, son adresse, sa date de téléchargement, sa taille et son empreinte SHA-256.
"""

import hashlib
import os
import sys
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.chemins import Chemins
from src.lecture_yaml import lire_modele

FICHIER_SOURCES = "sources.yaml"

ENTETE = """\
# Manifeste des sources (RG-05).
#
# SRC-01 à SRC-19 : catalogue de la section 7.1 du cahier des charges.
# SRC-xx-… : publications citées aux sections 14.2 et 14.3, rattachées à leur source parente
# du catalogue ; le titre reprend le libellé du lien dans le cahier.
# CDC : décisions de l'équipe (ÉQ) et propositions d'analyse (PROP) du cahier des charges.
# telechargement : procédure de « python -m scripts.download » pour les sources à adresse stable.
# fichiers : rempli par le script (adresse, date, taille, SHA-256) ; ne pas modifier à la main.
"""


def empreinte_sha256(chemin: Path) -> str:
    """Empreinte SHA-256 (hexadécimale) du fichier ``chemin``."""
    with chemin.open("rb") as flux:
        return hashlib.file_digest(flux, "sha256").hexdigest()


def empreinte_md5(chemin: Path) -> str:
    """Empreinte MD5 du fichier, pour la comparer à celle annoncée par une API (figshare)."""
    with chemin.open("rb") as flux:
        return hashlib.file_digest(flux, "md5").hexdigest()


class Ressource(BaseModel):
    """Un fichier à télécharger ; ``nom`` est le nom donné par l'API ou le nom local."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    nom: str = Field(min_length=1)
    url: str | None = Field(default=None, description="Adresse directe (méthode « direct »)")
    fichier: str | None = Field(default=None, description="Nom local, s'il diffère de ``nom``")

    @property
    def nom_local(self) -> str:
        """Nom du fichier dans ``data/raw/<source>/``."""
        return self.fichier or self.nom


class Telechargement(BaseModel):
    """Procédure de téléchargement automatique d'une source à adresse stable."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    methode: Literal["direct", "ckan", "figshare"]
    api: str | None = None
    jeu: str | None = Field(default=None, description="Identifiant du jeu de données CKAN")
    ressources: list[Ressource] = Field(min_length=1)

    @model_validator(mode="after")
    def _coherence(self) -> Self:
        if self.methode == "direct":
            sans_url = [r.nom for r in self.ressources if not r.url]
            if sans_url:
                raise ValueError(f"méthode direct : adresse manquante pour {', '.join(sans_url)}.")
        elif not self.api:
            raise ValueError(f"méthode {self.methode} : adresse de l'API (api) manquante.")
        if self.methode == "ckan" and not self.jeu:
            raise ValueError("méthode ckan : identifiant du jeu de données (jeu) manquant.")
        noms = [r.nom_local for r in self.ressources]
        if len(set(noms)) != len(noms):
            raise ValueError("deux ressources portent le même nom local.")
        return self


class Fichier(BaseModel):
    """Fichier présent dans ``data/raw/<source>/`` et son empreinte (RG-05)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    url: str | None = Field(default=None, description="None si le fichier a été déposé à la main")
    date_telechargement: date | None = None
    taille_octets: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    supprime_le: date | None = Field(
        default=None, description="Date de suppression volontaire du fichier local"
    )
    remplace_par: str | None = Field(
        default=None,
        description=(
            "Fichier dérivé (chemin relatif à la racine) qui rend la suppression sans risque : "
            "absent du poste (installation neuve), le fichier supprimé est retéléchargé"
        ),
    )
    note: str | None = None


class Source(BaseModel):
    """Une source de données ou une publication."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    identifiant: str = Field(min_length=1)
    titre: str = Field(min_length=1)
    url: str | None = None
    parent: str | None = Field(default=None, description="Source du catalogue 7.1 de rattachement")
    nature: str | None = None
    contenu: str | None = None
    format: str | None = None
    maille: str | None = None
    licence: str | None = None
    attribution: str | None = Field(
        default=None, description="Mention à afficher sous chaque carte qui utilise la source"
    )
    priorite: str | None = None
    archive: str | None = Field(
        default=None, description="Copie locale de la page dans data/raw/, ou motif de l'absence"
    )
    telechargement: Telechargement | None = None
    fichiers: dict[str, Fichier] = {}


class ManifesteSources(BaseModel):
    """Ensemble des sources, indexées par identifiant."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sources: dict[str, Source]

    @model_validator(mode="before")
    @classmethod
    def _injecter_identifiants(cls, donnees: object) -> object:
        if isinstance(donnees, dict) and isinstance(donnees.get("sources"), dict):
            donnees = {
                **donnees,
                "sources": {
                    cle: {"identifiant": cle, **val} if isinstance(val, dict) else val
                    for cle, val in donnees["sources"].items()
                },
            }
        return donnees

    @model_validator(mode="after")
    def _verifier_parents(self) -> Self:
        for identifiant, source in self.sources.items():
            if source.identifiant != identifiant:
                raise ValueError(f"{identifiant} : identifiant incohérent ({source.identifiant}).")
            if source.parent is None:
                continue
            parent = self.sources.get(source.parent)
            if parent is None:
                raise ValueError(f"{identifiant} : source parente {source.parent} inconnue.")
            if parent.parent is not None:
                raise ValueError(
                    f"{identifiant} : la source parente {source.parent} doit être une source du "
                    "catalogue, sans parente."
                )
        return self

    def inconnues(self, identifiants: Iterable[str]) -> list[str]:
        """Renvoie, triés, les identifiants absents du manifeste."""
        return sorted(set(identifiants) - set(self.sources))

    def avec(self, source: Source) -> Self:
        """Copie du manifeste où ``source`` remplace l'entrée de même identifiant."""
        return self.model_copy(update={"sources": {**self.sources, source.identifiant: source}})


def charger_sources(chemins: Chemins) -> ManifesteSources:
    """Lit et valide ``data/sources.yaml``."""
    return lire_modele(chemins.donnees / FICHIER_SOURCES, ManifesteSources)


def enregistrer_sources(chemins: Chemins, manifeste: ManifesteSources) -> None:
    """Écrit le manifeste dans ``data/sources.yaml`` (écriture complète puis remplacement)."""
    contenu = {
        "sources": {
            identifiant: source.model_dump(
                mode="json", exclude={"identifiant"}, exclude_none=True, exclude_defaults=True
            )
            for identifiant, source in manifeste.sources.items()
        }
    }
    texte = (
        ENTETE
        + "\n"
        + yaml.safe_dump(contenu, allow_unicode=True, sort_keys=False, width=sys.maxsize)
    )
    cible = chemins.donnees / FICHIER_SOURCES
    provisoire = cible.with_name(f".{cible.name}.provisoire")
    provisoire.write_text(texte, encoding="utf-8")
    os.replace(provisoire, cible)
