"""Scénarios enregistrés en YAML dans ``scenarios/`` (UC-SCN-02, UC-DAT-08).

Un scénario fige les paramètres de l'entreprise, les réglages des paramètres techniques, les
critères actifs, les seuils, les poids, la méthode de classement, les sites, et la version des
données utilisée. Rechargé, il est identique à l'enregistrement et indique sa version de
données ; s'il diffère de la version active, l'écart est signalé.
"""

import re
import unicodedata
from datetime import datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.chemins import Chemins
from src.data.versions import Versions
from src.lecture_yaml import lire_yaml, valider
from src.scenarios.config import charger_entreprise
from src.scenarios.entreprise import Valeur, mettre_a_jour_entreprise
from src.scenarios.parametres import Reglage, reglages_courants, remplacer_reglages

EXTENSION = ".yaml"


class ErreurScenario(Exception):
    """Scénario illisible ou refusé ; message en français."""


class Site(BaseModel):
    """Site candidat d'un scénario (section 13, table ``sites``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id_site: str = Field(min_length=1)
    nom: str = Field(min_length=1)
    type: str = Field(min_length=1)
    lon: float
    lat: float
    code_province: str | None = None
    impose: bool = False


class Scenario(BaseModel):
    """Contenu d'un fichier ``scenarios/<nom>.yaml``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    nom: str = Field(min_length=1)
    date: str = Field(min_length=1)
    auteur: str = Field(min_length=1)
    version_donnees: str | None
    parametres_entreprise: dict[str, Valeur]
    reglages: dict[str, Reglage] = {}
    criteres_actifs: list[str] = []
    seuils: dict[str, float] = {}
    poids: dict[str, float] = {}
    methode: str | None = None
    sites: list[Site] = []

    @field_validator("poids")
    @classmethod
    def _poids_positifs(cls, poids: dict[str, float]) -> dict[str, float]:
        negatifs = [c for c, p in poids.items() if p < 0]
        if negatifs:
            raise ValueError(f"poids négatifs : {', '.join(negatifs)}")
        return poids


def nom_de_fichier(nom: str) -> str:
    """« Scénario Meknès 2026 » → « scenario-meknes-2026.yaml »."""
    texte = unicodedata.normalize("NFKD", nom.strip())
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn").lower()
    texte = re.sub(r"[^a-z0-9]+", "-", texte).strip("-")
    if not texte:
        raise ErreurScenario(f"nom de scénario « {nom} » inutilisable : employez des lettres")
    return texte + EXTENSION


def scenario_courant(
    chemins: Chemins,
    nom: str,
    auteur: str,
    *,
    criteres_actifs: list[str] | None = None,
    seuils: dict[str, float] | None = None,
    poids: dict[str, float] | None = None,
    methode: str | None = None,
    sites: list[Site] | None = None,
) -> Scenario:
    """Scénario formé de l'état courant : paramètres, réglages et version active des données."""
    journal = Versions(chemins).journal()
    entreprise = charger_entreprise(chemins)
    return Scenario(
        nom=nom,
        date=datetime.now().isoformat(timespec="seconds"),
        auteur=auteur,
        version_donnees=journal[-1].id_version if journal else None,
        parametres_entreprise={i: p.valeur for i, p in entreprise.parametres.items()},
        reglages=reglages_courants(chemins),
        criteres_actifs=criteres_actifs or [],
        seuils=seuils or {},
        poids=poids or {},
        methode=methode,
        sites=sites or [],
    )


def enregistrer_scenario(chemins: Chemins, scenario: Scenario, remplacer: bool = False) -> Path:
    """Écrit le scénario ; un scénario de même nom n'est remplacé que sur demande."""
    chemin = chemins.scenarios / nom_de_fichier(scenario.nom)
    if chemin.exists() and not remplacer:
        raise ErreurScenario(
            f"un scénario « {scenario.nom} » existe déjà : choisissez un autre nom ou remplacez-le"
        )
    chemins.scenarios.mkdir(parents=True, exist_ok=True)
    texte = yaml.safe_dump(scenario.model_dump(mode="json"), allow_unicode=True, sort_keys=False)
    chemin.write_text(texte, encoding="utf-8")
    return chemin


def charger_scenario(chemins: Chemins, nom: str) -> Scenario:
    """Scénario enregistré sous ``nom``."""
    chemin = chemins.scenarios / nom_de_fichier(nom)
    if not chemin.is_file():
        raise ErreurScenario(f"scénario « {nom} » introuvable dans scenarios/")
    return valider(lire_yaml(chemin), Scenario, chemin.name)


def lister_scenarios(chemins: Chemins) -> list[Scenario]:
    """Scénarios enregistrés, du plus récent au plus ancien."""
    if not chemins.scenarios.is_dir():
        return []
    scenarios = [
        valider(lire_yaml(f), Scenario, f.name)
        for f in sorted(chemins.scenarios.glob(f"*{EXTENSION}"))
    ]
    return sorted(scenarios, key=lambda s: s.date, reverse=True)


def dernier_scenario(chemins: Chemins) -> Scenario | None:
    """Scénario le plus récent (chargé au lancement, UC-00)."""
    scenarios = lister_scenarios(chemins)
    return scenarios[0] if scenarios else None


def ecart_de_version(chemins: Chemins, scenario: Scenario) -> str | None:
    """Message si la version de données du scénario n'est plus la version active."""
    journal = Versions(chemins).journal()
    active = journal[-1].id_version if journal else None
    if scenario.version_donnees == active:
        return None
    return (
        f"le scénario « {scenario.nom} » a été calculé avec la version de données "
        f"{scenario.version_donnees or 'livrée'} ; la version active est {active or 'livrée'}"
    )


def appliquer_scenario(chemins: Chemins, scenario: Scenario, auteur: str) -> None:
    """Rend actifs les paramètres de l'entreprise et les réglages du scénario."""
    mettre_a_jour_entreprise(chemins, dict(scenario.parametres_entreprise), auteur)
    remplacer_reglages(chemins, dict(scenario.reglages))
