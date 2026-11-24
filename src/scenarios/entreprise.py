"""Paramètres de l'entreprise (section 14.1, UC-ENT-01, RG-15, RG-16).

Les valeurs ne sont jamais supposées : elles sont saisies par l'entreprise, contrôlées (type,
choix, bornes de ``controles.yaml``), puis écrites avec la date et l'auteur dans
``config/entreprise.local.yaml``, fichier local ignoré par Git. Le modèle livré
``config/entreprise.yaml`` n'est jamais modifié. Chaque mise à jour publie un événement
« paramètres modifiés », auquel les calculs qui en dépendent s'abonnent (RG-16).
"""

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import yaml

from src.chemins import Chemins
from src.scenarios.config import (
    FICHIER_ENTREPRISE_LOCAL,
    ParametreEntreprise,
    ParametresEntreprise,
    SaisiesEntreprise,
    charger_controles,
    charger_entreprise,
)

Valeur = float | str | list[str] | dict[str, list[str]] | None
CLES_SITES = ("imposes", "exclus")


class ErreurEntreprise(Exception):
    """Valeur refusée ; le message dit quoi corriger."""


@dataclass(frozen=True)
class ParametresModifies:
    """Événement « paramètres modifiés » (RG-16)."""

    identifiants: tuple[str, ...]
    avant: dict[str, Valeur]
    apres: dict[str, Valeur]
    date: date
    auteur: str


_abonnes: list[Callable[[ParametresModifies], None]] = []


def abonner(fonction: Callable[[ParametresModifies], None]) -> Callable[[], None]:
    """Appelle ``fonction`` à chaque modification ; renvoie la fonction de désabonnement."""
    _abonnes.append(fonction)
    return lambda: _abonnes.remove(fonction)


def _nombre(valeur: object) -> float | None:
    if isinstance(valeur, bool):
        return None
    if isinstance(valeur, int | float):
        return float(valeur)
    try:
        return float(str(valeur).strip().replace(",", "."))
    except ValueError:
        return None


def controler_valeur(chemins: Chemins, parametre: ParametreEntreprise, valeur: object) -> Valeur:
    """Valeur contrôlée et normalisée ; ``None`` efface la saisie."""
    if valeur is None or (isinstance(valeur, str) and not valeur.strip()):
        return None
    nom = f"{parametre.identifiant} · {parametre.libelle}"
    if parametre.type == "sites":
        if not isinstance(valeur, dict) or set(valeur) - set(CLES_SITES):
            raise ErreurEntreprise(f"{nom} : indiquez les listes {' et '.join(CLES_SITES)}")
        return {
            cle: [str(s).strip() for s in valeur.get(cle, []) if str(s).strip()]
            for cle in CLES_SITES
        }
    texte = str(valeur).strip()
    if parametre.type in ("choix", "nombre_ou_choix") and texte in parametre.choix:
        return texte
    if parametre.type == "choix":
        raise ErreurEntreprise(f"{nom} : choisissez parmi {', '.join(parametre.choix)}")
    nombre = _nombre(valeur)
    if nombre is None:
        attendu = " ou une classe (" + ", ".join(parametre.choix) + ")" if parametre.choix else ""
        raise ErreurEntreprise(f"{nom} : « {valeur} » n'est pas un nombre{attendu}")
    fourchette = (
        charger_controles(chemins).fourchettes.get("entreprise", {}).get(parametre.identifiant)
    )
    if fourchette is not None and not fourchette.contient(nombre):
        raise ErreurEntreprise(f"{nom} : {nombre:g} {parametre.unite} refusé ; {fourchette.motif}")
    return nombre


ENTETE_LOCAL = (
    "# Saisies d'Atlantic Biochar (onglet Paramètres), écrites par l'outil.\n"
    "# Fichier local, ignoré par Git, lu par-dessus le modèle livré vide config/entreprise.yaml.\n"
)


def _ecrire(chemins: Chemins, entreprise: ParametresEntreprise) -> None:
    """Écrit les valeurs saisies dans le fichier local ; le modèle livré n'est jamais modifié."""
    saisies = SaisiesEntreprise(
        date_modification=entreprise.date_modification,
        auteur=entreprise.auteur,
        valeurs={i: p.valeur for i, p in entreprise.parametres.items() if p.valeur is not None},
    )
    chemin = chemins.config / FICHIER_ENTREPRISE_LOCAL
    corps = yaml.safe_dump(saisies.model_dump(mode="json"), allow_unicode=True, sort_keys=False)
    provisoire = chemin.with_name(f".{chemin.name}.provisoire")
    provisoire.write_text(ENTETE_LOCAL + corps, encoding="utf-8")
    os.replace(provisoire, chemin)


def mettre_a_jour_entreprise(
    chemins: Chemins, valeurs: dict[str, object], auteur: str, jour: date | None = None
) -> tuple[ParametresEntreprise, ParametresModifies | None]:
    """Enregistre les valeurs saisies, datées et signées ; publie l'événement RG-16.

    Args:
        chemins: dossiers de l'outil.
        valeurs: identifiant (PAR-xx) → valeur saisie (``None`` pour effacer).
        auteur: personne qui modifie.
        jour: date de la modification (par défaut, aujourd'hui).

    Returns:
        Les paramètres enregistrés, et l'événement (None si rien n'a changé).
    """
    if not auteur.strip():
        raise ErreurEntreprise("indiquez l'auteur de la modification")
    entreprise = charger_entreprise(chemins)
    inconnus = [i for i in valeurs if i not in entreprise.parametres]
    if inconnus:
        raise ErreurEntreprise(f"paramètres inconnus : {', '.join(inconnus)}")
    nouvelles = {
        i: controler_valeur(chemins, entreprise.parametres[i], v) for i, v in valeurs.items()
    }
    changes = tuple(i for i, v in nouvelles.items() if entreprise.parametres[i].valeur != v)
    if not changes:
        return entreprise, None
    jour = jour or date.today()
    parametres = {
        i: p.model_copy(update={"valeur": nouvelles[i]}) if i in changes else p
        for i, p in entreprise.parametres.items()
    }
    mis_a_jour = entreprise.model_copy(
        update={"parametres": parametres, "date_modification": jour, "auteur": auteur.strip()}
    )
    _ecrire(chemins, mis_a_jour)
    evenement = ParametresModifies(
        identifiants=changes,
        avant={i: entreprise.parametres[i].valeur for i in changes},
        apres={i: nouvelles[i] for i in changes},
        date=jour,
        auteur=auteur.strip(),
    )
    for fonction in list(_abonnes):
        fonction(evenement)
    return charger_entreprise(chemins), evenement
