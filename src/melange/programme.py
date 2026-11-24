"""Mélange de résidus de coût minimal pour un site et une capacité K (section 11.2.4, UC-MIX-01).

min Σ (CL − λ · BN · y) x  sous  Σ x = K ; 0 ≤ x ≤ M ; Σ_p x(p, r) ≤ α · K pour chaque résidu ;
Σ (a_r − ā) x ≤ 0 (cendres) ; Σ (h_r − h̄) x ≤ 0 (humidité), résolu par scipy.optimize.linprog
(HiGHS). Les variables sont les tonnages achetés aux couples du bassin (coût livré sous le prix
plafond). Une contrainte dont le paramètre n'est pas saisi (PAR-51, 52, 53) n'est pas appliquée,
et c'est dit. Si le problème est infaisable, il est relancé en relâchant une contrainte à la fois
pour indiquer laquelle bloque.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import linprog

COLONNES_MELANGE = [
    "code_province",
    "code_residu",
    "tonnage",
    "part",
    "cout_livre",
    "cendres",
    "humidite",
    "disponible",
]


@dataclass(frozen=True)
class Contraintes:
    """Paramètres du mélange (section 14.1) ; None : contrainte non appliquée."""

    capacite: float  # K, t MS/an
    part_maximale: float | None = None  # α, fraction de K (PAR-51 / 100)
    cendres_maximales: float | None = None  # ā, % MS
    humidite_maximale: float | None = None  # h̄, %
    lambda_carbone: float = 0.0  # PAR-54, DH/t CO₂e


@dataclass(frozen=True)
class Melange:
    """Résultat du programme linéaire."""

    faisable: bool
    tableau: pd.DataFrame
    cout_moyen: float | None
    cendres_moyennes: float | None
    humidite_moyenne: float | None
    bilan_moyen: float | None
    bloquantes: list[str] = field(default_factory=list)
    non_appliquees: list[str] = field(default_factory=list)
    message: str = ""


NOMS = {
    "part": "part maximale d'un résidu (PAR-51)",
    "cendres": "cendres moyennes maximales (PAR-52)",
    "humidite": "humidité moyenne maximale (PAR-53)",
}


def _resoudre(
    couples: pd.DataFrame, c: Contraintes, actives: set[str], avec_carbone: bool
) -> np.ndarray | None:
    n = len(couples)
    cout = couples["cout_livre"].to_numpy(dtype=float)
    if avec_carbone:
        cout = cout - c.lambda_carbone * couples["carbone_t"].to_numpy(dtype=float)
    a_ub, b_ub = [], []
    if "part" in actives and c.part_maximale is not None:
        for residu in couples["code_residu"].unique():
            a_ub.append((couples["code_residu"] == residu).to_numpy(dtype=float))
            b_ub.append(c.part_maximale * c.capacite)
    if "cendres" in actives and c.cendres_maximales is not None:
        a_ub.append(couples["cendres"].to_numpy(dtype=float) - c.cendres_maximales)
        b_ub.append(0.0)
    if "humidite" in actives and c.humidite_maximale is not None:
        a_ub.append(couples["humidite"].to_numpy(dtype=float) - c.humidite_maximale)
        b_ub.append(0.0)
    resultat = linprog(
        cout,
        A_ub=np.array(a_ub) if a_ub else None,
        b_ub=np.array(b_ub) if b_ub else None,
        A_eq=np.ones((1, n)),
        b_eq=np.array([c.capacite]),
        bounds=list(zip(np.zeros(n), couples["disponible"].to_numpy(dtype=float), strict=True)),
        method="highs",
    )
    return resultat.x if resultat.status == 0 else None


def melange_optimal(couples: pd.DataFrame, c: Contraintes) -> Melange:
    """Mélange de coût minimal.

    Args:
        couples: couples du bassin : ``code_province``, ``code_residu``, ``disponible``
            (M, t MS/an), ``cout_livre`` (DH/t MS), ``cendres`` (% MS), ``humidite`` (%) et,
            si λ > 0, ``carbone_t`` (BN × y, t CO₂e retirées par t MS).
        c: capacité et contraintes.
    """
    non_appliquees = [
        NOMS[nom]
        for nom, valeur in (
            ("part", c.part_maximale),
            ("cendres", c.cendres_maximales),
            ("humidite", c.humidite_maximale),
        )
        if valeur is None
    ]
    vide = pd.DataFrame(columns=COLONNES_MELANGE)
    disponible = float(couples["disponible"].sum()) if not couples.empty else 0.0
    if disponible < c.capacite:
        return Melange(
            False,
            vide,
            None,
            None,
            None,
            None,
            ["capacité K"],
            non_appliquees,
            f"le bassin n'offre que {disponible:,.0f} t MS/an sous le prix plafond pour "
            f"{c.capacite:,.0f} t MS/an visées".replace(",", " "),
        )
    avec_carbone = c.lambda_carbone > 0 and "carbone_t" in couples
    toutes = set(NOMS)
    x = _resoudre(couples, c, toutes, avec_carbone)
    if x is None:
        bloquantes = [
            NOMS[n] for n in NOMS if _resoudre(couples, c, toutes - {n}, avec_carbone) is not None
        ]
        message = (
            "problème infaisable ; il devient faisable en relâchant : " + ", ".join(bloquantes)
            if bloquantes
            else "problème infaisable même en relâchant une seule contrainte à la fois"
        )
        return Melange(False, vide, None, None, None, None, bloquantes, non_appliquees, message)
    retenus = couples.assign(tonnage=x)
    retenus = retenus[retenus["tonnage"] > 0].copy()
    total = retenus["tonnage"].sum()
    retenus["part"] = retenus["tonnage"] / total

    def moyenne(colonne: str) -> float | None:
        if colonne not in retenus or retenus[colonne].isna().any():
            return None
        return float((retenus[colonne] * retenus["tonnage"]).sum() / total)

    return Melange(
        True,
        retenus[[*COLONNES_MELANGE, *(["carbone_t"] if "carbone_t" in retenus else [])]]
        .sort_values("tonnage", ascending=False)
        .reset_index(drop=True),
        moyenne("cout_livre"),
        moyenne("cendres"),
        moyenne("humidite"),
        moyenne("carbone_t"),
        [],
        non_appliquees,
        "mélange de coût minimal trouvé",
    )
