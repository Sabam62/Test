"""Couples du bassin d'un site, avec les propriétés utiles au mélange (section 11.2.4)."""

import pandas as pd

from src.data.provenance import ValeurACompleter
from src.data.tables_reference import TableLongue
from src.logistique.couts import Courbe


def _propriete(residus: TableLongue, residu: str, parametre: str) -> float | None:
    precisions = residus.precisions(residu, parametre)
    precision = "" if "" in precisions or len(precisions) != 1 else precisions[0]
    try:
        return float(residus.valeur(residu, parametre, precision).lire_nombre())
    except (ValeurACompleter, KeyError, TypeError):
        return None


def couples_du_bassin(
    courbe: Courbe, residus: TableLongue, bilans: pd.DataFrame | None, id_site: str
) -> tuple[pd.DataFrame, list[str]]:
    """Couples sous le prix plafond, avec cendres, humidité et carbone retiré par t MS.

    Un couple dont les cendres ou l'humidité manquent est exclu et listé (RG-06) ; le carbone
    retiré (BN × y) n'est fourni que si le bilan climat du couple est calculé.

    Returns:
        Table des couples et motifs d'exclusion.
    """
    bassin = courbe.bassin
    lignes, motifs = [], []
    for ligne in bassin.itertuples():
        cendres = _propriete(residus, ligne.code_residu, "cendres")
        humidite = _propriete(residus, ligne.code_residu, "humidite")
        if cendres is None or humidite is None:
            manque = "cendres" if cendres is None else "humidite"
            motifs.append(f"{ligne.code_residu} · {manque} à compléter : couples exclus du mélange")
            continue
        carbone = None
        if bilans is not None and not bilans.empty:
            b = bilans[
                (bilans["id_site"] == id_site)
                & (bilans["code_province"] == ligne.code_province)
                & (bilans["code_residu"] == ligne.code_residu)
            ]
            y = _propriete(residus, ligne.code_residu, "rendement_pyrolyse")
            if not b.empty and pd.notna(b["BN"].iloc[0]) and y is not None:
                carbone = float(b["BN"].iloc[0]) * y
        lignes.append(
            {
                "code_province": ligne.code_province,
                "code_residu": ligne.code_residu,
                "disponible": float(ligne.tonnage),
                "cout_livre": float(ligne.cout_livre),
                "cendres": cendres,
                "humidite": humidite,
                "carbone_t": carbone,
            }
        )
    return pd.DataFrame(lignes), sorted(set(motifs))
