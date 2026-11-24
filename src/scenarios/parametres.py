"""Paramètres techniques : valeur courante, valeur par défaut, retour au défaut (UC-SCN-01).

Les valeurs par défaut sont celles de ``config/parametres.yaml`` (section 14.3), jamais
modifiées. Un réglage de l'entreprise est enregistré à part, dans
``config/parametres_modifies.yaml``, avec sa source, sa date et son auteur (RG-18) ; le retour
au défaut le supprime. Une composante se désigne par « PAR-20:basse ».
"""

import os
from dataclasses import dataclass
from datetime import date

import yaml
from pydantic import BaseModel, ConfigDict, Field

from src.chemins import Chemins
from src.data.provenance import Statut, ValeurSourcee
from src.lecture_yaml import lire_yaml, valider
from src.scenarios.config import Parametre, charger_parametres

FICHIER_MODIFIES = "parametres_modifies.yaml"
SEPARATEUR_COMPOSANTE = ":"


class ErreurParametre(Exception):
    """Réglage refusé ; message en français."""


class Reglage(BaseModel):
    """Valeur réglée par l'entreprise à la place de la valeur par défaut."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    valeur: float | str
    source: str = Field(min_length=1)
    date: date
    auteur: str = Field(min_length=1)
    statut: Statut = Statut.TERRAIN
    note: str | None = None


class Reglages(BaseModel):
    """Contenu de ``config/parametres_modifies.yaml``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reglages: dict[str, Reglage] = {}


@dataclass(frozen=True)
class EtatParametre:
    """Un paramètre (ou une composante) tel qu'affiché sur l'écran « Paramètres »."""

    identifiant: str
    libelle: str
    defaut: ValeurSourcee | None
    courante: ValeurSourcee | None
    modifie: bool
    calcul: str | None = None


def _lire_reglages(chemins: Chemins) -> Reglages:
    chemin = chemins.config / FICHIER_MODIFIES
    if not chemin.is_file():
        return Reglages()
    return valider(lire_yaml(chemin) or {}, Reglages, FICHIER_MODIFIES)


def _ecrire_reglages(chemins: Chemins, reglages: Reglages) -> None:
    chemin = chemins.config / FICHIER_MODIFIES
    entete = (
        "# Réglages des paramètres techniques par l'entreprise (écran « Paramètres »).\n"
        "# Écrit par l'outil ; le retour au défaut supprime l'entrée. Défauts : parametres.yaml.\n"
    )
    corps = yaml.safe_dump(reglages.model_dump(mode="json"), allow_unicode=True, sort_keys=True)
    provisoire = chemin.with_name(f".{chemin.name}.provisoire")
    provisoire.write_text(entete + corps, encoding="utf-8")
    os.replace(provisoire, chemin)


def _defaut(parametre: Parametre, composante: str | None) -> ValeurSourcee:
    if composante is not None:
        return parametre.composante(composante)
    if parametre.calcul is not None:
        raise ErreurParametre(
            f"{parametre.identifiant} est calculé par l'outil ({parametre.calcul.methode}) : "
            "réglez ses entrées"
        )
    if parametre.valeur is None:
        raise ErreurParametre(
            f"{parametre.identifiant} a des composantes : désignez-en une "
            f"({', '.join(parametre.composantes or {})})"
        )
    return parametre.valeur


def _separer(identifiant: str) -> tuple[str, str | None]:
    base, _, composante = identifiant.partition(SEPARATEUR_COMPOSANTE)
    return base, composante or None


def _appliquer(defaut: ValeurSourcee, reglage: Reglage) -> ValeurSourcee:
    return ValeurSourcee(
        nom=defaut.nom,
        valeur=reglage.valeur,
        unite=defaut.unite,
        source_id=reglage.source,
        annee=reglage.date.year,
        statut=reglage.statut,
        note=reglage.note or f"réglé par {reglage.auteur} le {reglage.date.isoformat()}",
    )


def valeur_courante(chemins: Chemins, identifiant: str) -> ValeurSourcee:
    """Valeur utilisée par les calculs : le réglage de l'entreprise, sinon le défaut."""
    base, composante = _separer(identifiant)
    defaut = _defaut(charger_parametres(chemins)[base], composante)
    reglage = _lire_reglages(chemins).reglages.get(identifiant)
    return _appliquer(defaut, reglage) if reglage else defaut


def etat_parametres(chemins: Chemins) -> list[EtatParametre]:
    """Tous les paramètres techniques avec défaut, valeur courante et état de modification."""
    reglages = _lire_reglages(chemins).reglages
    etats = []
    for identifiant, parametre in charger_parametres(chemins).parametres.items():
        if parametre.calcul is not None:
            etats.append(
                EtatParametre(
                    identifiant, parametre.libelle, None, None, False, parametre.calcul.methode
                )
            )
            continue
        cles = [None] if parametre.valeur is not None else list(parametre.composantes or {})
        for composante in cles:
            cle = identifiant if composante is None else f"{identifiant}:{composante}"
            defaut = _defaut(parametre, composante)
            reglage = reglages.get(cle)
            courante = _appliquer(defaut, reglage) if reglage else defaut
            libelle = (
                parametre.libelle if composante is None else f"{parametre.libelle} · {composante}"
            )
            etats.append(EtatParametre(cle, libelle, defaut, courante, reglage is not None))
    return etats


def regler_parametre(
    chemins: Chemins,
    identifiant: str,
    valeur: object,
    source: str,
    auteur: str,
    jour: date | None = None,
    statut: Statut = Statut.TERRAIN,
    note: str | None = None,
) -> ValeurSourcee:
    """Remplace la valeur par défaut d'un paramètre ; source et auteur obligatoires (RG-18).

    ``statut`` et ``note`` : « Terrain » et la date par défaut (saisie de l'entreprise) ;
    « Hypothèse » pour une valeur de démonstration (:mod:`src.scenarios.demo`).
    """
    base, composante = _separer(identifiant)
    defaut = _defaut(charger_parametres(chemins)[base], composante)
    if not str(source).strip():
        raise ErreurParametre(f"{identifiant} : source obligatoire (RG-18)")
    if not str(auteur).strip():
        raise ErreurParametre(f"{identifiant} : indiquez l'auteur du réglage")
    choix = charger_parametres(chemins)[base].choix
    if choix:
        nouvelle: float | str = str(valeur).strip()
        if nouvelle not in choix:
            raise ErreurParametre(f"{identifiant} : choisissez parmi {', '.join(choix)}")
    elif isinstance(defaut.valeur, str) or (defaut.valeur is None and defaut.unite == "—"):
        nouvelle = str(valeur).strip()
    else:
        try:
            nouvelle = float(str(valeur).strip().replace(",", "."))
        except ValueError:
            raise ErreurParametre(f"{identifiant} : « {valeur} » n'est pas un nombre") from None
    reglage = Reglage(
        valeur=nouvelle,
        source=str(source).strip(),
        date=jour or date.today(),
        auteur=auteur,
        statut=statut,
        note=note,
    )
    reglages = _lire_reglages(chemins).reglages
    _ecrire_reglages(chemins, Reglages(reglages={**reglages, identifiant: reglage}))
    return _appliquer(defaut, reglage)


def revenir_au_defaut(chemins: Chemins, identifiant: str) -> ValeurSourcee:
    """Supprime le réglage : la valeur par défaut de ``parametres.yaml`` s'applique de nouveau."""
    base, composante = _separer(identifiant)
    defaut = _defaut(charger_parametres(chemins)[base], composante)
    reglages = dict(_lire_reglages(chemins).reglages)
    if reglages.pop(identifiant, None) is not None:
        _ecrire_reglages(chemins, Reglages(reglages=reglages))
    return defaut


def reglages_courants(chemins: Chemins) -> dict[str, Reglage]:
    """Réglages en vigueur (copiés dans chaque scénario)."""
    return dict(_lire_reglages(chemins).reglages)


def remplacer_reglages(chemins: Chemins, reglages: dict[str, Reglage]) -> None:
    """Remplace tous les réglages (chargement d'un scénario)."""
    for identifiant in reglages:
        base, composante = _separer(identifiant)
        _defaut(charger_parametres(chemins)[base], composante)
    _ecrire_reglages(chemins, Reglages(reglages=reglages))
