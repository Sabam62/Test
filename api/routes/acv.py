"""Bilan climat (UC-ACV-01 à 03) : état du projet Brightway, bilans par couple et par site.

Le projet Brightway est reconstruit quand les données, les paramètres ou ``config/acv.yaml``
changent (clé de cache, RG-13). Tout bilan affiché rappelle son unité fonctionnelle, son
scénario de référence et le standard appliqué (RG-07).
"""

import hashlib
from threading import Lock
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

from api.dependances import obtenir_chemins
from api.routes.logistique import LogistiqueDep, cle_logistique
from api.routes.potentiel import CalculDep
from api.serialisation import lignes
from src.acv.calcul import ResultatAcv, preparer_acv
from src.acv.config import FICHIER_CONFIG, charger_config_acv
from src.chemins import Chemins
from src.logistique.couts import Blocage, Terme

routeur = APIRouter(prefix="/acv", tags=["acv"])
CheminsDep = Annotated[Chemins, Depends(obtenir_chemins)]
_cache: dict[str, ResultatAcv] = {}
_verrou = Lock()


def _empreinte(chemins: Chemins) -> str:
    fichier = chemins.config / FICHIER_CONFIG
    return hashlib.sha256(fichier.read_bytes()).hexdigest() if fichier.is_file() else "absent"


def resultat_acv(chemins: CheminsDep, calcul: CalculDep, logistique: LogistiqueDep) -> ResultatAcv:
    """Projet Brightway et scores unitaires, reconstruits seulement si les entrées changent."""
    cle = hashlib.sha256(f"{cle_logistique(chemins)}|{_empreinte(chemins)}".encode()).hexdigest()
    with _verrou:
        if cle not in _cache:
            entrees = calcul.entrees
            _cache.clear()
            _cache[cle] = preparer_acv(
                charger_config_acv(chemins),
                entrees.residus_retenus(),  # variantes PAR-62, PAR-63
                entrees.tables.facteurs_emission,
                entrees.catalogue.residus.codes,
                logistique.lire,
                entrees.config.unites_fraction,
                entrees.config.moins_fiable,
            )
        return _cache[cle]


AcvDep = Annotated[ResultatAcv, Depends(resultat_acv)]


def _contexte(acv: ResultatAcv) -> dict[str, object]:
    """Rappels de la RG-07 et permanence retenue."""
    import bw2data as bd

    permanence = acv.entrees.permanence
    return {
        "unite_fonctionnelle": acv.config.unite_fonctionnelle,
        "standard": acv.config.standard_par_defaut,
        "classe_temperature": acv.entrees.classe,
        "permanence": permanence.valeur if isinstance(permanence, Terme) else None,
        "permanence_motif": None if isinstance(permanence, Terme) else permanence,
        "etapes": acv.config.etapes,
        "projet": acv.config.projet,
        "dossier_brightway": str(bd.projects.dir.parent),
        "methode": acv.config.methode,
    }


def _scenarios(acv: ResultatAcv, noms: dict[str, str]) -> list[dict[str, object]]:
    return [
        {"code_residu": code, "nom": noms.get(code, code), "scenario": p.scenario}
        for code, p in acv.entrees.residus.items()
    ]


def _noms_residus(calcul: CalculDep) -> dict[str, str]:
    residus = calcul.entrees.tables.residus
    return {c: str(residus.valeur(c, "nom").lire()) for c in calcul.entrees.catalogue.residus.codes}


@routeur.get("/etat")
def etat(acv: AcvDep, calcul: CalculDep) -> dict[str, object]:
    """Projet Brightway, méthode, scores unitaires et rappels de la RG-07."""
    return _contexte(acv) | {
        "scores_unitaires": acv.scores.scores,
        "scenarios": _scenarios(acv, _noms_residus(calcul)),
    }


@routeur.get("/sites/{id_site}")
def bilans_site(
    id_site: str, acv: AcvDep, logistique: LogistiqueDep, calcul: CalculDep
) -> dict[str, object]:
    """Bilan de chaque couple vers le site, par résidu, et bilan du site (RG-08)."""
    distances = logistique.distances_site(id_site)
    if distances.empty:
        raise HTTPException(404, f"site « {id_site} » inconnu")
    table = acv.bilans(distances)
    noms_r = _noms_residus(calcul)
    provinces = calcul.entrees.referentiel.provinces
    noms_p = dict(zip(provinces["code_province"], provinces["nom_fr"], strict=True))
    table = table.assign(
        nom_province=table["code_province"].map(noms_p),
        nom_residu=table["code_residu"].map(noms_r),
    )
    calcules = table[table["BN"].notna()]
    par_residu = []
    for code, groupe in table.groupby("code_residu", sort=True):
        valides = groupe[groupe["BN"].notna()]
        par_residu.append(
            {
                "code_residu": code,
                "nom": noms_r.get(str(code), str(code)),
                "scenario": acv.entrees.residus[str(code)].scenario,
                "couples": len(groupe),
                "couples_calcules": len(valides),
                "BN_median": float(valides["BN"].median()) if not valides.empty else None,
                "BN_min": float(valides["BN"].min()) if not valides.empty else None,
                "BN_max": float(valides["BN"].max()) if not valides.empty else None,
                "motif": None if not valides.empty else str(groupe["motif"].iloc[0]),
            }
        )
    site_bilan = None
    motif_site = None
    try:
        courbe, _ = logistique.courbe(id_site)
        retenus = courbe.retenus.merge(
            calcules, on=["code_province", "code_residu"], suffixes=("", "_acv")
        )
        if not retenus.empty:
            poids = retenus["tonnage_retenu"]
            site_bilan = {
                terme: float((retenus[terme] * poids).sum() / poids.sum())
                for terme in ("E_col", "E_pre", "E_tr", "E_pyr", "E_ep", "E_ref", "stock", "BN")
            } | {"tonnage": float(poids.sum()), "couples": len(retenus)}
        else:
            motif_site = "aucun couple du bassin retenu pour K n'a de bilan calculé"
    except Blocage as blocage:
        motif_site = f"bassin d'approvisionnement non calculé : {str(blocage).splitlines()[0]}"
    motifs = (
        table.loc[table["BN"].isna(), "motif"]
        .str.split(" | ", regex=False)
        .explode()
        .value_counts()
    )
    return _contexte(acv) | {
        "site": id_site,
        "couples": len(table),
        "couples_calcules": len(calcules),
        "par_residu": par_residu,
        "bilan_site": site_bilan,
        "motif_site": motif_site,
        "a_saisir": [{"motif": m, "couples": int(n)} for m, n in motifs.items() if m],
        "bilans": lignes(calcules.sort_values("BN", ascending=False).head(200)),
    }


@routeur.get("/chaine")
def chaine(
    province: str, residu: str, site: str, acv: AcvDep, logistique: LogistiqueDep
) -> dict[str, object]:
    """Contributions d'une chaîne, recalculées par le modèle Brightway paramétré (UC-ACV-03)."""
    distances = logistique.distances_site(site)
    ligne = distances[
        (distances["code_province"] == province) & (distances["code_residu"] == residu)
    ]
    if ligne.empty:
        raise HTTPException(404, f"chaîne {province} × {residu} → {site} inconnue")
    bilan = acv.bilans(ligne).iloc[0]
    if pd.isna(bilan["BN"]):
        return _contexte(acv) | {"bloque": True, "a_saisir": bilan["motif"].split(" | ")}
    etapes = acv.chaine_brightway(residu, float(ligne["distance_km"].iloc[0]))
    kg = acv.config.kg_par_tonne
    return _contexte(acv) | {
        "bloque": False,
        "bilan": {k: (None if pd.isna(v) else v) for k, v in bilan.items()},
        "brightway": {nom: valeur / kg for nom, valeur in etapes.items()},
        "scenario": acv.entrees.residus[residu].scenario,
    }
