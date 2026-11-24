"""Critères des gisements (couples province × résidu) pour leur classement (UC-DEC-04).

Les critères de niveau G de la section 9 : A1 (gisement mobilisable M), A2 (densité de M), A3
(part libre d'usage concurrent), B1 à B4 (propriétés du résidu), B5 (éligibilité EBC, filtre),
et, pour un site choisi, C1 (coût livré), C6 (marge) et D1 (bilan net). Les couples classés sont
ceux qui ont un gisement théorique T calculé. Une valeur qui manque porte son motif (RG-14).
"""

from collections.abc import Callable

import pandas as pd

from src.data.provenance import ValeurACompleter, ValeurSourcee
from src.data.tables_reference import TableLongue

SEPARATEUR = "|"


def identifiant(province: str, residu: str) -> str:
    """Identifiant d'un couple dans la matrice : « province|résidu »."""
    return f"{province}{SEPARATEUR}{residu}"


def _propriete(residus: TableLongue, residu: str, parametre: str) -> float | str:
    try:
        precisions = residus.precisions(residu, parametre)
        precision = "" if "" in precisions or len(precisions) != 1 else precisions[0]
        return float(residus.valeur(residu, parametre, precision).lire_nombre())
    except (ValeurACompleter, KeyError, TypeError):
        return f"{residu} · {parametre} à compléter"


def _poser(
    v: dict[str, float | None],
    mo: dict[str, str | None],
    code: str,
    valeur: float | str | None,
    motif: str = "valeur manquante",
) -> None:
    """Valeur d'un critère, ou son motif si elle manque (texte ou None)."""
    if isinstance(valeur, str):
        v[code], mo[code] = None, valeur
    elif valeur is None:
        v[code], mo[code] = None, motif
    else:
        v[code], mo[code] = float(valeur), None


def _par_couple(table: pd.DataFrame, colonne: str = "valeur") -> dict[tuple[str, str], float]:
    return {
        (str(l.code_province), str(l.code_residu)): float(getattr(l, colonne))
        for l in table.itertuples()  # noqa: E741
    }


def matrice_gisements(
    theorique: pd.DataFrame,
    mobilisable: pd.DataFrame,
    densite: pd.DataFrame,
    exclus_m: pd.DataFrame,
    residus: TableLongue,
    concurrence: TableLongue,
    national: str,
    couts_site: pd.DataFrame | None,
    motif_couts: str | None,
    bilans_site: pd.DataFrame | None,
    lire: Callable[[str], ValeurSourcee],
    prix: tuple[str, str],
    pourcentage: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Valeurs (couples × critères G) et motifs des valeurs manquantes.

    Args:
        theorique: T de la campagne de référence (couples classés).
        mobilisable: M de la campagne de référence.
        densite: densité de M (t MS/km²/an).
        exclus_m: couples dont M est exclu, avec le motif (module M1).
        residus: ``residus.csv`` actif.
        concurrence: ``concurrence.csv`` actif.
        national: code des valeurs nationales de ``concurrence.csv``.
        couts_site: coûts livrés vers le site choisi (module M2), ou None.
        motif_couts: motif si les coûts ne sont pas calculés.
        bilans_site: bilans climat vers le site choisi (module M3), ou None.
        lire: valeur d'un paramètre (prix du biochar et du crédit, C6).
        prix: identifiants de PAR-55 et PAR-56.
        pourcentage: conversion des fractions en %.
    """
    m = _par_couple(mobilisable)
    d = _par_couple(densite)
    motifs_m = {
        (str(l.code_province), str(l.code_residu)): str(l.motif)
        for l in exclus_m[exclus_m["indicateur"] == "M"].itertuples()  # noqa: E741
    }
    cl = _par_couple(couts_site, "cout_livre") if couts_site is not None else {}
    bn = (
        {
            (str(l.code_province), str(l.code_residu)): (l.BN, l.motif)
            for l in bilans_site.itertuples()  # noqa: E741
        }
        if bilans_site is not None
        else {}
    )
    prix_valeurs = []
    for p in prix:
        v = lire(p).valeur
        prix_valeurs.append(float(v) if isinstance(v, int | float) else f"{p} à renseigner")
    valeurs: dict[str, dict[str, float | None]] = {}
    motifs: dict[str, dict[str, str | None]] = {}
    for ligne in theorique.itertuples():
        couple = (str(ligne.code_province), str(ligne.code_residu))
        r = couple[1]
        cle = identifiant(*couple)
        v: dict[str, float | None] = {}
        mo: dict[str, str | None] = {}

        _poser(v, mo, "A1", m.get(couple), motifs_m.get(couple, "M non calculé"))
        _poser(v, mo, "A2", d.get(couple), motifs_m.get(couple, "M non calculé"))
        u: float | str = f"{r} · part_utilisee à compléter"
        for cle_u in (couple, (national, r)):
            try:
                valeur_u = concurrence.valeur(cle_u, "part_utilisee").valeur
            except KeyError:
                continue
            if valeur_u is not None:
                u = (1 - float(valeur_u)) * pourcentage
                break
        _poser(v, mo, "A3", u)
        _poser(v, mo, "B1", _propriete(residus, r, "carbone"))
        _poser(v, mo, "B2", _propriete(residus, r, "cendres"))
        _poser(v, mo, "B3", _propriete(residus, r, "humidite"))
        y = _propriete(residus, r, "rendement_pyrolyse")
        _poser(v, mo, "B4", y)
        eligible = residus.valeur(r, "eligible_ebc").valeur
        _poser(
            v,
            mo,
            "B5",
            None if eligible is None else (1.0 if str(eligible) == "oui" else 0.0),
            f"{r} · eligible_ebc à compléter (liste positive EBC, SRC-14)",
        )
        _poser(v, mo, "C1", cl.get(couple), motif_couts or "coût livré non calculé pour ce couple")
        bilan, motif_bilan = bn.get(couple, (None, "bilan climat non calculé"))
        bilan = None if bilan is None or pd.isna(bilan) else float(bilan)
        _poser(v, mo, "D1", bilan, (motif_bilan or "bilan climat non calculé").split(" | ")[0])
        if isinstance(y, str):
            _poser(v, mo, "C6", y)
        elif any(isinstance(p, str) for p in prix_valeurs):
            _poser(v, mo, "C6", next(p for p in prix_valeurs if isinstance(p, str)))
        elif couple not in cl:
            _poser(v, mo, "C6", None, motif_couts or "coût livré non calculé")
        elif bilan is None:
            _poser(v, mo, "C6", None, "bilan climat non calculé")
        else:
            _poser(v, mo, "C6", prix_valeurs[0] * y + prix_valeurs[1] * bilan * y - cl[couple])  # type: ignore[operator]
        valeurs[cle], motifs[cle] = v, mo
    index = pd.Index(list(valeurs), name="couple")
    return (
        pd.DataFrame.from_dict(valeurs, orient="index", dtype=float).reindex(index),
        pd.DataFrame.from_dict(motifs, orient="index", dtype=object).reindex(index),
    )
