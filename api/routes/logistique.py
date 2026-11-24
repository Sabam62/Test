"""Sites et logistique (UC-LOG-01 à 04) : sites candidats, état d'OSRM, courbe et bassin.

Les calculs sont faits par :mod:`src.logistique` ; la matrice des distances est mise en cache
sur disque (RG-13). Une valeur manquante (« À compléter », paramètre de l'entreprise non
renseigné) ne produit pas d'erreur : la réponse liste les valeurs à saisir et où les saisir
(RG-14, RG-15).
"""

import hashlib
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Annotated

import geopandas as gpd
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependances import obtenir_chemins
from api.routes.potentiel import CalculDep, cle_cache
from api.serialisation import lignes
from src.chemins import Chemins
from src.data.versions import Versions
from src.logistique.calcul import ResultatLogistique, calculer_logistique
from src.logistique.config import FICHIER_CONFIG, charger_config_logistique
from src.logistique.couts import SEPARATEUR_BLOCAGES, Blocage
from src.logistique.distances import (
    ErreurDistances,
    commande_osrm,
    isodistance,
    osrm_disponible,
)
from src.logistique.sites import ErreurSite, ajouter_site, supprimer_site
from src.scenarios.config import FICHIER_ENTREPRISE_LOCAL

routeur = APIRouter(prefix="/logistique", tags=["logistique"])
CheminsDep = Annotated[Chemins, Depends(obtenir_chemins)]


@lru_cache(maxsize=2)
def _provinces(fichier: Path, empreinte: float) -> gpd.GeoDataFrame:
    return gpd.read_file(fichier)


def obtenir_provinces(chemins: CheminsDep) -> gpd.GeoDataFrame:
    """Polygones des provinces (``data/processed/provinces.gpkg``)."""
    fichier = chemins.preparees / "provinces.gpkg"
    if not fichier.is_file():
        raise HTTPException(503, "provinces absentes : lancez « python -m scripts.prepare »")
    return _provinces(fichier, fichier.stat().st_mtime)


ProvincesDep = Annotated[gpd.GeoDataFrame, Depends(obtenir_provinces)]
_cache: dict[str, ResultatLogistique] = {}
_verrou = Lock()


def _empreinte(fichier: Path) -> str:
    return hashlib.sha256(fichier.read_bytes()).hexdigest() if fichier.is_file() else "absent"


def cle_logistique(chemins: Chemins) -> str:
    """Clé du cache : gisements, configuration, saisies, sites et état d'OSRM (RG-13)."""
    config = charger_config_logistique(chemins)
    elements = [
        cle_cache(chemins),
        _empreinte(chemins.config / FICHIER_CONFIG),
        _empreinte(chemins.config / FICHIER_ENTREPRISE_LOCAL),
        _empreinte(chemins.config / config.sites.fichier_utilisateur),
        _empreinte(chemins.saisies / config.sites.fichier_agropoles),
        _empreinte(chemins.preparees / config.rattachement.sortie),
        str(osrm_disponible(config)),
    ]
    return hashlib.sha256("|".join(elements).encode()).hexdigest()


def resultat_logistique(
    chemins: CheminsDep, calcul: CalculDep, provinces: ProvincesDep
) -> ResultatLogistique:
    """Logistique calculée sur les gisements courants, depuis le cache si rien n'a changé."""
    cle = cle_logistique(chemins)
    with _verrou:
        if cle not in _cache:
            entrees = calcul.entrees
            try:
                resultat = calculer_logistique(
                    chemins,
                    calcul.resultat.reference(
                        charger_config_logistique(chemins).indicateur_gisement
                    ),
                    entrees.residus_retenus(),  # variantes PAR-62, PAR-63
                    entrees.tables.concurrence,
                    entrees.catalogue.code_national,
                    entrees.config.moins_fiable,
                    provinces,
                    prix_observes=Versions(chemins).lire("prix_observes"),
                    noms_residus=_noms_residus(calcul),
                )
            except (ErreurDistances, ErreurSite, Blocage) as erreur:
                raise HTTPException(503, str(erreur)) from None
            _cache.clear()
            _cache[cle] = resultat
        return _cache[cle]


LogistiqueDep = Annotated[ResultatLogistique, Depends(resultat_logistique)]


def _noms_provinces(calcul: CalculDep) -> dict[str, str]:
    provinces = calcul.entrees.referentiel.provinces
    return dict(zip(provinces["code_province"], provinces["nom_fr"], strict=True))


def _noms_residus(calcul: CalculDep) -> dict[str, str]:
    residus = calcul.entrees.tables.residus
    return {c: str(residus.valeur(c, "nom").lire()) for c in calcul.entrees.catalogue.residus.codes}


@routeur.get("/etat")
def etat(chemins: CheminsDep) -> dict[str, object]:
    """État du routage : OSRM joignable, adresse, commande pour le démarrer."""
    config = charger_config_logistique(chemins)
    return {
        "osrm": osrm_disponible(config),
        "url": config.osrm.url,
        "commande": commande_osrm(),
    }


def _site_json(ligne: dict[str, object], noms: dict[str, str]) -> dict[str, object]:
    code = ligne.get("code_province")
    return {**ligne, "nom_province": noms.get(str(code)) if code else None}


@routeur.get("/sites")
def sites(logistique: LogistiqueDep, calcul: CalculDep) -> dict[str, object]:
    """Sites candidats, agropoles à placer, méthode des distances (UC-LOG-01, 02)."""
    noms = _noms_provinces(calcul)
    tous = logistique.sites.sites
    c3 = {s: logistique.tonnage_rayon(s) for s in tous["id_site"]}
    liste = [
        _site_json(ligne, noms) | {"tonnage_rayon_c3": c3[str(ligne["id_site"])]}
        for ligne in lignes(tous)
    ]
    p = logistique.config.parametres
    return {
        "sites": liste,
        "a_completer": lignes(logistique.sites.a_completer),
        "methode": logistique.matrice.methode,
        "message": logistique.matrice.message,
        "calibration": (
            logistique.matrice.calibration.__dict__ if logistique.matrice.calibration else None
        ),
        "rayon_c3": logistique.lire(p.rayon_c3).valeur,
        "transport_bloque": logistique.blocage_camion,
    }


class NouveauSite(BaseModel):
    """Site ajouté par coordonnées ou par clic sur la carte (UC-LOG-01)."""

    nom: str = Field(min_length=1)
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    auteur: str = Field(min_length=1)


@routeur.post("/sites")
def nouveau_site(
    corps: NouveauSite, chemins: CheminsDep, provinces: ProvincesDep
) -> dict[str, object]:
    """Ajoute un site de l'utilisateur ; il entre dans tous les calculs."""
    try:
        return ajouter_site(
            chemins,
            charger_config_logistique(chemins),
            provinces,
            corps.nom,
            corps.lon,
            corps.lat,
            corps.auteur,
        )
    except ErreurSite as erreur:
        raise HTTPException(400, str(erreur)) from None


@routeur.delete("/sites/{id_site}")
def retirer_site(id_site: str, chemins: CheminsDep) -> dict[str, str]:
    """Retire un site ajouté par l'utilisateur."""
    try:
        supprimer_site(chemins, charger_config_logistique(chemins), id_site)
    except ErreurSite as erreur:
        raise HTTPException(404, str(erreur)) from None
    return {"retire": id_site}


def _site(logistique: ResultatLogistique, id_site: str) -> dict[str, object]:
    choix = logistique.sites.sites[logistique.sites.sites["id_site"] == id_site]
    if choix.empty:
        raise HTTPException(404, f"site « {id_site} » inconnu")
    return lignes(choix)[0]


def _motifs(exclus: pd.DataFrame) -> list[dict[str, object]]:
    """Motifs d'exclusion regroupés : un motif, le nombre de couples, les résidus concernés."""
    if exclus.empty:
        return []
    groupes = exclus.groupby("motif")
    return [
        {"motif": motif, "couples": len(g), "residus": sorted(g["code_residu"].unique())}
        for motif, g in sorted(groupes, key=lambda x: -len(x[1]))
    ]


@routeur.get("/sites/{id_site}/courbe")
def courbe(id_site: str, logistique: LogistiqueDep, calcul: CalculDep) -> dict[str, object]:
    """Courbe d'approvisionnement, coût pour atteindre K et bassin (UC-LOG-03, 04, RG-10)."""
    site = _site(logistique, id_site)
    base = {
        "site": site,
        "methode": logistique.matrice.methode,
        "message": logistique.matrice.message,
        "gisements_calcules": len(logistique.gisements),
    }
    try:
        resultat, exclus = logistique.courbe(id_site)
    except Blocage as blocage:
        return base | {"bloque": True, "a_saisir": str(blocage).split(SEPARATEUR_BLOCAGES)}
    noms_p, noms_r = _noms_provinces(calcul), _noms_residus(calcul)
    points = resultat.points.assign(
        nom_province=resultat.points["code_province"].map(noms_p),
        nom_residu=resultat.points["code_residu"].map(noms_r),
        dans_bassin=resultat.points["cout_livre"] <= resultat.plafond,
    )
    retenus = resultat.retenus
    return base | {
        "bloque": False,
        "capacite": resultat.capacite,
        "plafond": resultat.plafond,
        "points": lignes(points),
        "tonnage_total": resultat.tonnage_total,
        "tonnage_sous_plafond": resultat.tonnage_sous_plafond,
        "atteignable": resultat.atteignable,
        "manque": resultat.manque,
        "cout_moyen_k": resultat.cout_moyen_k,
        "cout_marginal_k": resultat.cout_marginal_k,
        "distance_moyenne_k": (
            float(
                (retenus["distance_km"] * retenus["tonnage_retenu"]).sum()
                / retenus["tonnage_retenu"].sum()
            )
            if not retenus.empty
            else None
        ),
        "distance_max_bassin": (
            float(resultat.bassin["distance_km"].max()) if not resultat.bassin.empty else None
        ),
        "exclus": _motifs(exclus),
    }


@routeur.get("/sites/{id_site}/bassin")
def bassin(id_site: str, logistique: LogistiqueDep, calcul: CalculDep) -> dict[str, object]:
    """Gisements du bassin (GeoJSON des points de rattachement) pour la carte (UC-LOG-04)."""
    site = _site(logistique, id_site)
    try:
        resultat, _ = logistique.courbe(id_site)
    except Blocage as blocage:
        return {"site": site, "bloque": True, "a_saisir": str(blocage).split(SEPARATEUR_BLOCAGES)}
    points = resultat.bassin.merge(
        logistique.rattachements[["code_province", "code_residu", "lon", "lat", "methode"]],
        on=["code_province", "code_residu"],
        suffixes=("", "_point"),
    )
    noms_p, noms_r = _noms_provinces(calcul), _noms_residus(calcul)
    entites = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [p["lon"], p["lat"]]},
            "properties": {
                "code_province": p["code_province"],
                "nom_province": noms_p.get(str(p["code_province"])),
                "code_residu": p["code_residu"],
                "nom_residu": noms_r.get(str(p["code_residu"])),
                "tonnage": p["tonnage"],
                "tonnage_retenu": p["tonnage_retenu"],
                "cout_livre": p["cout_livre"],
                "distance_km": p["distance_km"],
                "rattachement": p["methode_point"],
            },
        }
        for p in lignes(points)
    ]
    distance_max = float(resultat.bassin["distance_km"].max()) if entites else None
    calibration = logistique.matrice.calibration
    zone = (
        isodistance(
            float(site["lon"]),
            float(site["lat"]),
            distance_max,
            calibration.coefficient,
            logistique.config,
        )
        if distance_max and calibration
        else None
    )
    return {
        "site": site,
        "bloque": False,
        "gisements": {"type": "FeatureCollection", "features": entites},
        "distance_max_bassin": distance_max,
        "isodistance": zone,
        "coefficient_detour": calibration.coefficient if calibration else None,
    }
