"""Scénarios de démonstration (soutenance) : chargement en un clic, retour aux données réelles.

Un scénario de démonstration (``scenarios/demo/demo-<n>.yaml``) fixe des paramètres de
l'entreprise, des réglages techniques et des réglages de la décision ; il hérite des valeurs
manquantes communes de ``scenarios/demo/hypotheses.yaml``. Rien de l'utilisateur n'est
modifié : le chargement construit une copie de travail (le « miroir », ``data/cache/demo/``),
y enregistre ces valeurs par les mêmes fonctions que l'interface (versions, provenance), et
l'outil travaille sur cette copie tant que la démonstration est chargée. Une valeur déjà connue
n'est jamais remplacée : seules les valeurs « À compléter » sont complétées.

``config/entreprise.local.yaml``, ``config/parametres_modifies.yaml``,
``config/decision.local.yaml``, ``data/`` et le projet Brightway de l'utilisateur ne sont
jamais écrits ; seul le pointeur ``config/demo.local.yaml`` (fichier local) désigne le scénario
chargé, et « Quitter la démonstration » le retire.
"""

import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.chemins import Chemins
from src.data.provenance import A_COMPLETER, Statut
from src.data.sources import Source, charger_sources, enregistrer_sources
from src.data.versions import Versions
from src.decision.config import charger_catalogue_criteres, charger_config_decision
from src.decision.reglages import ReglagesUtilisateur, enregistrer_reglages
from src.lecture_yaml import lire_modele, lire_yaml, valider
from src.scenarios.entreprise import mettre_a_jour_entreprise
from src.scenarios.parametres import regler_parametre

FICHIER_CONFIG = "demo.yaml"
EXTENSION = ".yaml"
TEMOIN = ".miroir_demo"
NATIONAL = "NATIONAL"  # code_province des lignes nationales de concurrence.csv


class ErreurDemo(Exception):
    """Scénario de démonstration illisible ou introuvable ; message en français."""


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ConfigDemo(_Strict):
    """Contenu de ``config/demo.yaml``."""

    dossier: str = Field(min_length=1)
    hypotheses: str = Field(min_length=1)
    miroirs: str = Field(min_length=1)
    pointeur: str = Field(min_length=1)
    marqueur: str = Field(min_length=1)
    fichiers_exclus: list[str]
    auteur: str = Field(min_length=1)
    suffixe_projet_brightway: str = Field(min_length=1)
    mention: str = Field(min_length=1)
    bandeau: str = Field(min_length=1)


class ValeurDemo(_Strict):
    """Valeur complétée pour la démonstration, avec sa provenance."""

    valeur: float | str
    statut: Statut = Statut.HYPOTHESE
    source_id: str | None = None
    annee: int | None = None
    precision: str = ""
    note: str = Field(min_length=1)


class CalendrierDemo(_Strict):
    """Parts mensuelles de disponibilité d'un résidu (12 mois)."""

    mois: list[float]  # une part par colonne de mois de calendrier.csv (config/versions.yaml)
    statut: Statut = Statut.HYPOTHESE
    source_id: str | None = None
    annee: int | None = None
    note: str = Field(min_length=1)


class Hypotheses(_Strict):
    """Contenu de ``scenarios/demo/hypotheses.yaml``."""

    sources: dict[str, dict[str, str]] = {}
    reglages: dict[str, ValeurDemo] = {}
    residus: dict[str, dict[str, ValeurDemo]] = {}
    concurrence: dict[str, dict[str, ValeurDemo]] = {}
    facteurs_emission: dict[str, dict[str, ValeurDemo]] = {}
    calendrier: dict[str, CalendrierDemo] = {}


class ParametreDemo(_Strict):
    """Paramètre de l'entreprise fixé par un scénario de démonstration."""

    valeur: float | str
    note: str = Field(min_length=1)


class DecisionDemo(_Strict):
    """Réglages de la décision d'un scénario (poids absents : 1)."""

    actifs: list[str] | None = None
    poids: dict[str, float] = {}
    methode: str | None = None
    note: str | None = None


class FichierScenarioDemo(_Strict):
    """Contenu d'un fichier ``scenarios/demo/demo-<n>.yaml``."""

    nom: str = Field(min_length=1)
    description: str = Field(min_length=1)
    base: str | None = None
    entreprise: dict[str, ParametreDemo] = {}
    reglages: dict[str, ValeurDemo] = {}
    decision: DecisionDemo | None = None

    @field_validator("entreprise")
    @classmethod
    def _identifiants(cls, valeurs: dict[str, ParametreDemo]) -> dict[str, ParametreDemo]:
        mauvais = [i for i in valeurs if not i.startswith("PAR-")]
        if mauvais:
            raise ValueError(f"identifiants inattendus : {', '.join(mauvais)}")
        return valeurs


@dataclass(frozen=True)
class ScenarioDemo:
    """Scénario résolu : héritage (``base``) appliqué."""

    identifiant: str
    nom: str
    description: str
    entreprise: dict[str, ParametreDemo]
    reglages: dict[str, ValeurDemo]
    decision: DecisionDemo


@dataclass(frozen=True)
class DemoActive:
    """Scénario de démonstration chargé."""

    identifiant: str
    nom: str
    bandeau: str
    date: str
    racine: Path


@dataclass
class RapportChargement:
    """Ce que le chargement a complété, et les valeurs connues laissées intactes."""

    completees: list[str] = field(default_factory=list)
    ignorees: list[str] = field(default_factory=list)


def charger_config_demo(chemins: Chemins) -> ConfigDemo:
    """Lit et valide ``config/demo.yaml``."""
    return lire_modele(chemins.config / FICHIER_CONFIG, ConfigDemo)


def _dossier(chemins: Chemins, config: ConfigDemo) -> Path:
    return chemins.racine / config.dossier


def charger_hypotheses(chemins: Chemins) -> Hypotheses:
    """Valeurs manquantes communes à tous les scénarios de démonstration."""
    config = charger_config_demo(chemins)
    fichier = _dossier(chemins, config) / config.hypotheses
    return valider(lire_yaml(fichier), Hypotheses, fichier.name)


def _lire_fichier(chemins: Chemins, identifiant: str) -> FichierScenarioDemo:
    config = charger_config_demo(chemins)
    fichier = _dossier(chemins, config) / f"{identifiant}{EXTENSION}"
    if identifiant == Path(config.hypotheses).stem or not fichier.is_file():
        raise ErreurDemo(f"scénario de démonstration « {identifiant} » introuvable")
    return valider(lire_yaml(fichier), FichierScenarioDemo, fichier.name)


def charger_scenario_demo(chemins: Chemins, identifiant: str) -> ScenarioDemo:
    """Scénario de démonstration, héritage de sa ``base`` résolu."""
    chaine: list[FichierScenarioDemo] = []
    courant: str | None = identifiant
    while courant is not None:
        if len(chaine) > len(lister_identifiants(chemins)):
            raise ErreurDemo(f"héritage circulaire depuis « {identifiant} »")
        fichier = _lire_fichier(chemins, courant)
        chaine.append(fichier)
        courant = fichier.base
    entreprise: dict[str, ParametreDemo] = {}
    reglages: dict[str, ValeurDemo] = {}
    decision = DecisionDemo()
    for fichier in reversed(chaine):
        entreprise |= fichier.entreprise
        reglages |= fichier.reglages
        if fichier.decision is not None:
            decision = fichier.decision
    return ScenarioDemo(
        identifiant, chaine[0].nom, chaine[0].description, entreprise, reglages, decision
    )


def lister_identifiants(chemins: Chemins) -> list[str]:
    """Identifiants des scénarios de démonstration, dans l'ordre des noms de fichier."""
    config = charger_config_demo(chemins)
    dossier = _dossier(chemins, config)
    if not dossier.is_dir():
        return []
    return sorted(f.stem for f in dossier.glob(f"*{EXTENSION}") if f.name != config.hypotheses)


def lister_scenarios_demo(chemins: Chemins) -> list[ScenarioDemo]:
    """Tous les scénarios de démonstration, résolus."""
    return [charger_scenario_demo(chemins, i) for i in lister_identifiants(chemins)]


# --- Copie de travail ----------------------------------------------------------------------


def _miroir(chemins: Chemins, config: ConfigDemo, identifiant: str) -> Path:
    return chemins.racine / config.miroirs / identifiant


def lier_dossier(source: Path, lien: Path) -> None:
    """Lie ``lien`` au dossier ``source`` sans le copier (data/raw/ pèse plusieurs centaines de Mo).

    Sous Windows, un lien symbolique exige le mode développeur ou des droits d'administrateur :
    à défaut, une jonction de répertoire (sans droit particulier) la remplace. Supprimer la copie
    de travail supprime le lien, jamais le contenu de ``source`` (``shutil.rmtree`` ne suit ni
    les liens ni les jonctions).
    """
    try:
        os.symlink(source, lien, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        import _winapi  # module standard de Python sous Windows

        _winapi.CreateJunction(str(source), str(lien))


def _copier_donnees(reel: Chemins, cible: Path, config: ConfigDemo) -> None:
    """Copie config/ (sans les fichiers locaux) et data/ ; data/raw/ est lié, jamais écrit."""
    if cible.exists():
        if not (cible / TEMOIN).is_file():
            raise ErreurDemo(f"{cible} existe et n'est pas une copie de démonstration : arrêt")
        shutil.rmtree(cible)
    cible.mkdir(parents=True)
    (cible / TEMOIN).write_text("copie de travail de la démonstration\n", encoding="utf-8")
    shutil.copytree(
        reel.config, cible / "config", ignore=shutil.ignore_patterns(*config.fichiers_exclus)
    )
    donnees = cible / "data"
    donnees.mkdir()
    for nom in ("input", "manuelles", "processed", "versions"):
        if (reel.donnees / nom).is_dir():
            shutil.copytree(reel.donnees / nom, donnees / nom)
    for nom in ("sources.yaml", "versions.yaml"):
        if (reel.donnees / nom).is_file():
            shutil.copyfile(reel.donnees / nom, donnees / nom)
    # Cache des distances (RG-13) : la démonstration fonctionne sans OSRM.
    cache = reel.donnees / "cache" / "logistique"
    if cache.is_dir():
        shutil.copytree(cache, donnees / "cache" / "logistique")
    if reel.brutes.is_dir():
        lier_dossier(reel.brutes, donnees / "raw")
    (cible / "scenarios").mkdir()


def _projet_brightway(miroir: Chemins, config: ConfigDemo) -> None:
    """Projet Brightway propre à la démonstration : celui de l'utilisateur reste intact."""
    fichier = miroir.config / "acv.yaml"
    texte = fichier.read_text(encoding="utf-8")
    nouveau, n = re.subn(
        r"^(?P<cle>projet:\s*)(?P<nom>\S+)\s*$",
        lambda m: f"{m['cle']}{m['nom']}{config.suffixe_projet_brightway}",
        texte,
        count=1,
        flags=re.MULTILINE,
    )
    if n != 1:
        raise ErreurDemo("config/acv.yaml : clé « projet » introuvable")
    fichier.write_text(nouveau, encoding="utf-8")


def _note(config: ConfigDemo, valeur: ValeurDemo | CalendrierDemo) -> str:
    return f"{config.mention} ; {valeur.note}"


def _manquante(texte: object) -> bool:
    return str(texte).strip() in ("", A_COMPLETER)


def _completer_table(
    table: pd.DataFrame,
    valeurs: dict[str, dict[str, ValeurDemo]],
    colonne_code: str,
    filtre: dict[str, str],
    config: ConfigDemo,
    rapport: RapportChargement,
    nom_table: str,
) -> pd.DataFrame:
    """Complète les seules lignes « À compléter » ; une valeur connue est laissée intacte."""
    table = table.copy()
    for code, parametres in valeurs.items():
        for parametre, v in parametres.items():
            masque = (
                (table[colonne_code] == code)
                & (table["parametre"] == parametre)
                & (table["precision"] == v.precision)
            )
            for colonne, attendu in filtre.items():
                masque &= table[colonne] == attendu
            libelle = f"{nom_table} · {code} · {parametre}"
            if masque.sum() != 1:
                raise ErreurDemo(f"{libelle} : ligne introuvable ou en double")
            position = table.index[masque][0]
            if not _manquante(table.at[position, "valeur"]):
                rapport.ignorees.append(f"{libelle} (valeur connue conservée)")
                continue
            table.loc[position, ["min", "mode", "max", "loi"]] = ""
            table.at[position, "valeur"] = (
                f"{v.valeur:g}" if isinstance(v.valeur, float) else str(v.valeur)
            )
            table.at[position, "source_id"] = v.source_id or "DEMO"
            table.at[position, "annee"] = str(v.annee or date.today().year)
            table.at[position, "statut"] = v.statut.value
            table.at[position, "note"] = _note(config, v)
            rapport.completees.append(libelle)
    return table


def _completer_calendrier(
    table: pd.DataFrame,
    colonnes_mois: list[str],
    calendrier: dict[str, CalendrierDemo],
    config: ConfigDemo,
    rapport: RapportChargement,
) -> pd.DataFrame:
    """Ajoute les résidus absents du calendrier ; une ligne existante est laissée intacte."""
    lignes = []
    for code, c in calendrier.items():
        if len(c.mois) != len(colonnes_mois):
            raise ErreurDemo(
                f"calendrier · {code} : {len(colonnes_mois)} parts mensuelles attendues"
            )
        if (table["code_residu"] == code).any():
            rapport.ignorees.append(f"calendrier · {code} (ligne connue conservée)")
            continue
        ligne = {"code_residu": code}
        ligne |= {m: f"{p:g}" for m, p in zip(colonnes_mois, c.mois, strict=True)}
        ligne |= {
            "source_id": c.source_id or "DEMO",
            "annee": str(c.annee or date.today().year),
            "statut": c.statut.value,
            "note": _note(config, c),
        }
        lignes.append(ligne)
        rapport.completees.append(f"calendrier · {code}")
    if not lignes:
        return table
    return pd.concat([table, pd.DataFrame(lignes, columns=table.columns)], ignore_index=True)


def _completer_donnees(
    miroir: Chemins, hypotheses: Hypotheses, config: ConfigDemo, rapport: RapportChargement
) -> None:
    """Valeurs manquantes des tables : une version de la copie de travail (RG-17)."""
    manifeste = charger_sources(miroir)
    for identifiant, champs in hypotheses.sources.items():
        manifeste = manifeste.avec(Source(identifiant=identifiant, **champs))
    enregistrer_sources(miroir, manifeste)
    versions = Versions(miroir)
    tables = {
        "residus": _completer_table(
            versions.lire("residus"),
            hypotheses.residus,
            "code_residu",
            {},
            config,
            rapport,
            "residus",
        ),
        "concurrence": _completer_table(
            versions.lire("concurrence"),
            hypotheses.concurrence,
            "code_residu",
            {"code_province": NATIONAL},
            config,
            rapport,
            "concurrence",
        ),
        "facteurs_emission": _completer_table(
            versions.lire("facteurs_emission"),
            hypotheses.facteurs_emission,
            "code_activite",
            {},
            config,
            rapport,
            "facteurs_emission",
        ),
        "calendrier": _completer_calendrier(
            versions.lire("calendrier"),
            versions.definition("calendrier").valeurs.colonnes,  # type: ignore[union-attr]
            hypotheses.calendrier,
            config,
            rapport,
        ),
    }
    versions.enregistrer(tables, config.auteur, "valeurs manquantes de la démonstration")


def _regler(
    miroir: Chemins, reglages: dict[str, ValeurDemo], config: ConfigDemo, rapport: RapportChargement
) -> None:
    for identifiant, v in reglages.items():
        regler_parametre(
            miroir,
            identifiant,
            v.valeur,
            v.source_id or "DEMO",
            config.auteur,
            statut=v.statut,
            note=_note(config, v),
        )
        rapport.completees.append(f"paramètre · {identifiant}")


def _decision(miroir: Chemins, decision: DecisionDemo, config: ConfigDemo) -> None:
    catalogue = charger_catalogue_criteres(miroir)
    config_decision = charger_config_decision(miroir)
    reglages = ReglagesUtilisateur(
        actifs=decision.actifs,
        poids=decision.poids,
        methode=decision.methode,
        auteur=config.auteur,
    )
    enregistrer_reglages(miroir, reglages, catalogue, config_decision)


def charger_demo(reel: Chemins, identifiant: str) -> tuple[DemoActive, RapportChargement]:
    """Construit la copie de travail du scénario et la rend active.

    Args:
        reel: dossiers de l'utilisateur (jamais modifiés, sauf le pointeur local).
        identifiant: nom du fichier du scénario sans extension (« demo-1 »).

    Returns:
        La démonstration chargée et le détail des valeurs complétées.
    """
    config = charger_config_demo(reel)
    scenario = charger_scenario_demo(reel, identifiant)
    hypotheses = charger_hypotheses(reel)
    cible = _miroir(reel, config, identifiant)
    _copier_donnees(reel, cible, config)
    miroir = Chemins(cible)
    rapport = RapportChargement()
    _projet_brightway(miroir, config)
    _completer_donnees(miroir, hypotheses, config, rapport)
    _regler(miroir, hypotheses.reglages | scenario.reglages, config, rapport)
    mettre_a_jour_entreprise(
        miroir, {i: p.valeur for i, p in scenario.entreprise.items()}, config.auteur
    )
    _decision(miroir, scenario.decision, config)
    active = DemoActive(
        identifiant=identifiant,
        nom=scenario.nom,
        bandeau=config.bandeau,
        date=datetime.now().isoformat(timespec="seconds"),
        racine=cible,
    )
    contenu = {
        "identifiant": active.identifiant,
        "nom": active.nom,
        "date": active.date,
        "racine": str(cible.relative_to(reel.racine)),
    }
    texte = yaml.safe_dump(contenu, allow_unicode=True, sort_keys=False)
    (miroir.config / config.marqueur).write_text(texte, encoding="utf-8")
    entete = "# Scénario de démonstration chargé (fichier local, retiré en quittant la démo).\n"
    pointeur = reel.config / config.pointeur
    provisoire = pointeur.with_name(f".{pointeur.name}.provisoire")
    provisoire.write_text(entete + texte, encoding="utf-8")
    os.replace(provisoire, pointeur)
    return active, rapport


def _lire_active(fichier: Path) -> dict[str, str] | None:
    if not fichier.is_file():
        return None
    contenu = lire_yaml(fichier)
    return {str(c): str(v) for c, v in contenu.items()} if isinstance(contenu, dict) else None


def demo_active(chemins: Chemins) -> DemoActive | None:
    """Démonstration chargée : lue dans le marqueur (copie de travail) ou le pointeur (réel)."""
    config = charger_config_demo(chemins)
    contenu = _lire_active(chemins.config / config.marqueur)
    if contenu is not None:
        racine = chemins.racine
    else:
        contenu = _lire_active(chemins.config / config.pointeur)
        if contenu is None:
            return None
        racine = chemins.racine / contenu["racine"]
        if not (racine / TEMOIN).is_file():
            return None
    return DemoActive(
        contenu["identifiant"], contenu["nom"], config.bandeau, contenu["date"], racine
    )


def chemins_de_travail(reel: Chemins) -> Chemins:
    """Dossiers sur lesquels l'outil calcule : la copie de démonstration si elle est chargée."""
    active = demo_active(reel)
    return reel if active is None else Chemins(active.racine)


def quitter_demo(reel: Chemins) -> bool:
    """Retire le pointeur : l'outil revient aux données réelles, intactes. False si hors démo."""
    config = charger_config_demo(reel)
    pointeur = reel.config / config.pointeur
    if not pointeur.is_file():
        return False
    pointeur.unlink()
    return True


def bandeau_demo(chemins: Chemins) -> str | None:
    """Texte du bandeau de démonstration, ou None hors démonstration."""
    active = demo_active(chemins)
    return None if active is None else f"{active.bandeau} · {active.nom}"
