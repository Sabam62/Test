"""Saisie directe d'une valeur dans un tableau éditable (UC-DAT-07, RG-17 à RG-19).

La saisie est refusée sans source ni date (RG-18). Une valeur hors du domaine physique est
refusée ; une valeur hors de sa fourchette plausible est refusée tant qu'elle n'est pas
confirmée (RG-19). Chaque saisie crée une version (RG-17).
"""

from datetime import date

import pandas as pd

from src.data.excel import COLONNE_VERSION, VRAI
from src.data.versions import Version, Versions
from src.scenarios.config import Controles, Fourchette


class ErreurSaisie(Exception):
    """Saisie refusée ; le message dit quoi corriger."""


class ConfirmationRequise(ErreurSaisie):
    """Valeur hors fourchette (RG-19) : à confirmer avant enregistrement."""


def controler_fourchette(
    fourchette: Fourchette | None, nom: str, nombre: float, confirmer: bool
) -> None:
    """RG-19 : rejet hors du domaine physique ; confirmation hors de la fourchette plausible."""
    if fourchette is None:
        return
    rejet, a_confirmer = fourchette.controler(nom, nombre)
    if rejet:
        raise ErreurSaisie(rejet)
    if a_confirmer and not confirmer:
        raise ConfirmationRequise(f"{a_confirmer} : confirmez la saisie pour l'enregistrer")


def lire_date(texte: str) -> date:
    """Date ISO « AAAA-MM-JJ » ; erreur explicite sinon (RG-18)."""
    if not str(texte or "").strip():
        raise ErreurSaisie("date obligatoire (RG-18) : indiquez la date de la valeur")
    try:
        return date.fromisoformat(str(texte).strip())
    except ValueError:
        raise ErreurSaisie(f"date « {texte} » illisible : écrivez-la AAAA-MM-JJ") from None


def _texte_type(modele: pd.Series, valeur: object) -> object:
    """Valeur convertie au type de la colonne ``modele``."""
    if pd.api.types.is_bool_dtype(modele.dtype):
        return str(valeur).strip().lower() in VRAI
    if pd.api.types.is_numeric_dtype(modele.dtype):
        return float(str(valeur).replace(",", "."))
    return str(valeur)


def corriger_valeur(
    versions: Versions,
    controles: Controles,
    table: str,
    cle: dict[str, str],
    valeur: str,
    source: str,
    date_valeur: str,
    auteur: str,
    commentaire: str,
    confirmer: bool = False,
    textes: dict[str, list[str]] | None = None,
) -> Version | None:
    """Remplace la valeur d'une ligne existante, avec sa source et sa date.

    Args:
        versions: versions des données.
        controles: fourchettes de ``config/controles.yaml``.
        table: nom de la table (``config/versions.yaml``).
        cle: valeur de chaque colonne de la clé de la ligne.
        valeur: nouvelle valeur (première colonne contrôlée de la table).
        source: source de la valeur (lien, document ou « mesure interne »).
        date_valeur: date de la valeur, AAAA-MM-JJ.
        auteur: auteur de la modification.
        commentaire: commentaire de la version créée.
        confirmer: True pour enregistrer une valeur hors fourchette signalée (RG-19).
        textes: paramètres textuels de la table (catalogue des tables de référence) et leurs
            choix admis (liste vide : texte libre), par exemple le scénario de référence.
    """
    definition = versions.definition(table)
    if not str(source or "").strip():
        raise ErreurSaisie("source obligatoire (RG-18) : lien, document ou « mesure interne »")
    jour = lire_date(date_valeur)
    if definition.valeurs is None:
        raise ErreurSaisie(f"la table « {table} » n'a pas de colonne de valeur à saisir")
    manquantes = [c for c in definition.cle if c not in cle]
    if manquantes:
        raise ErreurSaisie(f"clé incomplète : indiquez {', '.join(manquantes)}")
    actuelle = versions.lire(table)
    masque = pd.Series(True, index=actuelle.index)
    for colonne in definition.cle:
        masque &= actuelle[colonne].astype(str) == str(cle[colonne])
    if not masque.any():
        raise ErreurSaisie(f"aucune ligne de « {table} » ne correspond à {cle}")
    position = actuelle.index[masque][0]
    nom = definition.valeurs.fourchette or str(
        actuelle.at[position, definition.valeurs.fourchette_selon or ""]
    )
    if textes is not None and nom in textes:
        choix = textes[nom]
        if not str(valeur).strip():
            raise ErreurSaisie(f"{nom} : valeur vide")
        if choix and str(valeur).strip() not in choix:
            raise ErreurSaisie(f"{nom} : choisissez parmi {', '.join(choix)}")
    else:
        try:
            nombre = float(str(valeur).replace(",", "."))
        except ValueError:
            raise ErreurSaisie(f"valeur « {valeur} » illisible : saisissez un nombre") from None
        fourchette = controles.fourchettes.get(definition.valeurs.table_fourchettes, {}).get(nom)
        controler_fourchette(fourchette, nom, nombre, confirmer)
    nouvelle = actuelle.copy()
    colonne_valeur = definition.valeurs.colonnes[0]
    nouvelle.at[position, colonne_valeur] = _texte_type(actuelle[colonne_valeur], valeur)
    nouvelle.at[position, definition.source] = str(source).strip()
    annee = (
        jour.year if pd.api.types.is_numeric_dtype(actuelle[definition.date]) else str(jour.year)
    )
    nouvelle.at[position, definition.date] = (
        annee if definition.format_date == "annee" else jour.isoformat()
    )
    if COLONNE_VERSION in nouvelle.columns:
        nouvelle.at[position, COLONNE_VERSION] = versions.prochain_identifiant()
    return versions.enregistrer({table: nouvelle}, auteur, commentaire)
