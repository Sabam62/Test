"""Gisements (UC-POT-01 à 03) : carte, tableau, synthèse nationale et couples exclus.

Les calculs sont faits par :mod:`src.potentiel` et gardés en cache (RG-13, section 16). La clé
du cache dépend de la version active des données, des réglages des paramètres techniques et
de ``config/potentiel.yaml`` : toute saisie ou tout import change la clé, donc le calcul.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Annotated

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

from api.dependances import charger_config_api, obtenir_chemins, obtenir_referentiel
from api.serialisation import lignes
from src.chemins import Chemins
from src.data.provenance import Statut
from src.data.provinces import Referentiel
from src.data.versions import Versions
from src.potentiel.config import FICHIER_CONFIG
from src.potentiel.entrees import EntreesPotentiel, charger_entrees
from src.potentiel.gisements import ResultatGisements, calculer_gisements, synthese_nationale
from src.potentiel.theorique import CAMPAGNE_REFERENCE
from src.scenarios.parametres import FICHIER_MODIFIES

routeur = APIRouter(prefix="/potentiel", tags=["potentiel"])
CheminsDep = Annotated[Chemins, Depends(obtenir_chemins)]
ReferentielDep = Annotated[Referentiel, Depends(obtenir_referentiel)]
TOUS = "tous"


@dataclass(frozen=True)
class Calcul:
    """Résultat mis en cache et ses entrées."""

    entrees: EntreesPotentiel
    resultat: ResultatGisements


_cache: dict[str, Calcul] = {}
_verrou = Lock()


def _empreinte(fichier: Path) -> str:
    return hashlib.sha256(fichier.read_bytes()).hexdigest() if fichier.is_file() else "absent"


def cle_cache(chemins: Chemins) -> str:
    """Clé du cache : version active, réglages techniques, configuration du potentiel."""
    journal = Versions(chemins).journal()
    elements = [
        str(chemins.racine),
        journal[-1].id_version if journal else "livrée",
        _empreinte(chemins.config / FICHIER_MODIFIES),
        _empreinte(chemins.config / FICHIER_CONFIG),
        _empreinte(Versions(chemins).fichier("production")),
    ]
    return hashlib.sha256("|".join(elements).encode()).hexdigest()


def calcul(chemins: CheminsDep, referentiel: ReferentielDep) -> Calcul:
    """Gisements calculés, depuis le cache si les entrées n'ont pas changé."""
    cle = cle_cache(chemins)
    with _verrou:
        if cle not in _cache:
            entrees = charger_entrees(chemins, referentiel)
            theorique = entrees.calcul_theorique().calculer(entrees.production)
            _cache.clear()
            _cache[cle] = Calcul(entrees, calculer_gisements(entrees, theorique))
        return _cache[cle]


CalculDep = Annotated[Calcul, Depends(calcul)]


def _verifier(calcul: Calcul, residu: str | None, indicateur: str) -> None:
    config = calcul.entrees.config
    if indicateur not in config.indicateurs:
        raise HTTPException(
            400, f"indicateur « {indicateur} » inconnu : {', '.join(config.indicateurs)}"
        )
    codes = calcul.entrees.catalogue.residus.codes
    if residu is not None and residu != TOUS and residu not in codes:
        raise HTTPException(400, f"résidu « {residu} » inconnu : {', '.join(codes)} ou « tous »")
    if residu == TOUS and not config.indicateurs[indicateur].additif:
        raise HTTPException(
            400,
            f"« {config.indicateurs[indicateur].libelle} » ne s'additionne pas entre résidus : "
            "choisissez un résidu",
        )


def _noms_residus(calcul: Calcul) -> dict[str, str]:
    residus = calcul.entrees.tables.residus
    return {c: str(residus.valeur(c, "nom").lire()) for c in calcul.entrees.catalogue.residus.codes}


@routeur.get("/indicateurs")
def indicateurs(calcul: CalculDep) -> dict[str, object]:
    """Indicateurs (libellé, unité, additivité) et résidus disponibles pour les filtres."""
    return {
        "indicateurs": [
            {"code": code, **definition.model_dump()}
            for code, definition in calcul.entrees.config.indicateurs.items()
        ],
        "residus": [{"code": c, "nom": n} for c, n in _noms_residus(calcul).items()],
    }


def _classes(valeurs: list[float], nombre: int) -> list[float]:
    """Bornes de la légende : quantiles des valeurs strictement positives (présentation)."""
    positives = np.array([v for v in valeurs if v > 0])
    if positives.size == 0:
        return []
    bornes = np.quantile(positives, np.linspace(0, 1, nombre + 1))
    return sorted({float(b) for b in bornes})


@routeur.get("/carte")
def carte(
    calcul: CalculDep,
    referentiel: ReferentielDep,
    chemins: CheminsDep,
    residu: str = "R01",
    indicateur: str = "T",
) -> dict[str, object]:
    """Valeur de chaque province pour un résidu (ou la somme des résidus) et un indicateur."""
    _verifier(calcul, residu, indicateur)
    resultat = calcul.resultat
    valeurs = resultat.reference(indicateur)
    exclus = resultat.exclus[resultat.exclus["indicateur"] == indicateur]
    if residu != TOUS:
        valeurs = valeurs[valeurs["code_residu"] == residu]
        exclus = exclus[exclus["code_residu"] == residu]
    provinces = []
    for _, province in referentiel.provinces.iterrows():
        code = province["code_province"]
        siennes = valeurs[valeurs["code_province"] == code]
        refus = exclus[exclus["code_province"] == code]
        provinces.append(
            {
                "code_province": code,
                "nom_fr": province["nom_fr"],
                "valeur": float(siennes["valeur"].sum()) if not siennes.empty else None,
                "statut": calcul.entrees.config.moins_fiable(
                    [Statut(s) for s in siennes["statut"]]
                ).value
                if not siennes.empty
                else None,
                "sources": sorted({s for v in siennes["sources"] for s in str(v).split("; ") if s}),
                "campagnes": sorted(
                    {c for v in siennes["campagnes"] for c in str(v).split("; ") if c}
                ),
                "previsionnel": bool(siennes["previsionnel"].any()),
                "residus_calcules": sorted(siennes["code_residu"]),
                "motifs": sorted(set(refus["motif"])),
            }
        )
    bornes = _classes(
        [p["valeur"] for p in provinces if p["valeur"] is not None],
        charger_config_api(chemins).classes_carte,
    )
    for p in provinces:
        p["classe"] = (
            None
            if p["valeur"] is None
            else int(np.searchsorted(bornes[1:-1], p["valeur"], side="right"))
            if bornes
            else 0
        )
    definition = calcul.entrees.config.indicateurs[indicateur]
    return {
        "residu": residu,
        "indicateur": indicateur,
        "libelle": definition.libelle,
        "unite": definition.unite,
        "campagne": CAMPAGNE_REFERENCE,
        "bornes": bornes,
        "provinces": provinces,
        "provinces_avec_valeur": sum(p["valeur"] is not None for p in provinces),
    }


@routeur.get("/tableau")
def tableau(
    calcul: CalculDep, referentiel: ReferentielDep, indicateur: str = "T"
) -> dict[str, object]:
    """Province × résidu pour un indicateur, avec provenance et motif de chaque cellule."""
    _verifier(calcul, None, indicateur)
    valeurs = calcul.resultat.reference(indicateur)
    exclus = calcul.resultat.exclus[calcul.resultat.exclus["indicateur"] == indicateur]
    par_cle = {(v.code_province, v.code_residu): v for v in valeurs.itertuples()}
    motifs = {(e.code_province, e.code_residu): e.motif for e in exclus.itertuples()}
    codes = calcul.entrees.catalogue.residus.codes
    lignes_tableau = []
    for _, province in referentiel.provinces.iterrows():
        cellules = {}
        for code in codes:
            v = par_cle.get((province["code_province"], code))
            cellules[code] = (
                {
                    "valeur": v.valeur,
                    "statut": v.statut,
                    "sources": v.sources,
                    "annee": v.campagnes,
                    "previsionnel": bool(v.previsionnel),
                    "note": v.note,
                }
                if v is not None
                else {"valeur": None, "motif": motifs.get((province["code_province"], code))}
            )
        lignes_tableau.append(
            {
                "code_province": province["code_province"],
                "nom_fr": province["nom_fr"],
                "cellules": cellules,
            }
        )
    definition = calcul.entrees.config.indicateurs[indicateur]
    return {
        "indicateur": indicateur,
        "libelle": definition.libelle,
        "unite": definition.unite,
        "residus": [{"code": c, "nom": n} for c, n in _noms_residus(calcul).items()],
        "lignes": lignes_tableau,
    }


@routeur.get("/synthese")
def synthese(calcul: CalculDep) -> dict[str, object]:
    """Totaux nationaux par résidu et par indicateur, et valeurs qui bloquent les calculs."""
    config = calcul.entrees.config
    par_residu = synthese_nationale(calcul.resultat, config)
    totaux = []
    for code, definition in config.indicateurs.items():
        if not definition.additif:
            continue
        sous = par_residu[(par_residu["indicateur"] == code) & par_residu["total"].notna()]
        totaux.append(
            {
                "indicateur": code,
                "libelle": definition.libelle,
                "unite": definition.unite,
                "total": float(sous["total"].sum()) if not sous.empty else None,
                "residus_calcules": sorted(sous["code_residu"]),
            }
        )
    exclus = calcul.resultat.exclus
    bloquants = (
        exclus.groupby("motif")
        .agg(couples=("code_province", "size"), residus=("code_residu", lambda r: sorted(set(r))))
        .reset_index()
        .sort_values("couples", ascending=False)
    )
    codes = calcul.entrees.catalogue.residus.codes
    return {
        "residus": len(codes),
        "totaux": totaux,
        "par_residu": lignes(par_residu),
        "bloquants": lignes(bloquants),
        "campagne": CAMPAGNE_REFERENCE,
    }


@routeur.get("/exclus")
def exclus(
    calcul: CalculDep, residu: str | None = None, indicateur: str | None = None
) -> list[dict[str, object]]:
    """Couples et indicateurs exclus, avec le motif (RG-06)."""
    table: pd.DataFrame = calcul.resultat.exclus
    if residu:
        table = table[table["code_residu"] == residu]
    if indicateur:
        table = table[table["indicateur"] == indicateur]
    return lignes(table)
